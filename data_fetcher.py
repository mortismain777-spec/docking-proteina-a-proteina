"""Identificadores y estructuras; ninguna llamada envía trabajos a HDOCK."""
from __future__ import annotations

import hashlib
import re
import shutil
import time
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ACCESSION = re.compile(r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-\d+)?$")
REFSEQ = re.compile(r'(?:[A-Z]{2}_\d+|[A-Z]{3,4}\d{5,})(?:\.\d+)?$')
ESMFOLD_URL = 'https://api.esmatlas.com/foldSequence/v1/pdb/'


class StructureUnavailable(ValueError):
    """No hay un modelo alternativo utilizable, sin detener el resto del lote."""


def session() -> requests.Session:
    """Reintentos limitados sólo para consultas idempotentes."""
    client = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    client.mount("https://", HTTPAdapter(max_retries=retry))
    client.headers["User-Agent"] = "DockingMatrix/0.1 (research desktop client)"
    return client


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pdb(path: Path) -> None:
    """Comprobación de formato mínima; no sustituye preparación estructural."""
    text = path.read_text(encoding="utf-8", errors="replace")
    atoms = [line for line in text.splitlines() if line.startswith("ATOM  ")]
    if not atoms:
        raise ValueError(f"{path.name}: no contiene registros ATOM de proteína.")
    for line in atoms:
        try:
            xyz = [float(line[a:b]) for a, b in [(30, 38), (38, 46), (46, 54)]]
            if not all(__import__('math').isfinite(v) for v in xyz):
                raise ValueError()
        except ValueError:
            raise ValueError(f"{path.name}: coordenadas ATOM inválidas.") from None


class StructureFetcher:
    def __init__(self, directory: Path, taxon: int = 9606, client=None, *, cache_directory=None,
                 allow_fallback=True, stop=None, callback=lambda event: None, esm_max_length=400,
                 provider_order=None, use_structure_cache=True, continue_provider_errors=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.taxon = int(taxon)
        self.client = client or session()
        self.remote_client = client if client is not None else requests.Session()
        self.remote_client.headers.update({'User-Agent':'DockingMatrix/0.3.0'}) if client is None else None
        from structure_cache import StructureCache
        self.cache = StructureCache(cache_directory or self.directory/'pdb_cache')
        self.allow_fallback, self.stop, self.callback = allow_fallback, stop, callback
        # Límite conservador de la app, configurable; no se presenta como garantía del servidor.
        self.esm_max_length = int(esm_max_length)
        self.last_call = {}
        self.chains = ''
        from provider_settings import validate_order
        self.provider_order=validate_order(provider_order) if provider_order is not None else None
        self.use_structure_cache=bool(use_structure_cache)
        self.continue_provider_errors=bool(continue_provider_errors)
        self.sequences={}

    def resolve(self, identifier: str) -> str:
        identifier = identifier.strip().upper()
        if ACCESSION.fullmatch(identifier) or REFSEQ.fullmatch(identifier):
            return identifier
        if len(identifier) > 150 or not re.fullmatch(r"[\w .()/-]+", identifier):
            raise ValueError("Usa un accession, símbolo de gen o nombre de proteína, sin comillas ni operadores de búsqueda.")
        queries = []
        if re.fullmatch(r'[A-Z0-9_.-]+', identifier):
            queries.append(f'gene_exact:{identifier} AND organism_id:{self.taxon}')
        queries.append(f'protein_name:"{identifier}" AND organism_id:{self.taxon}')
        expressions = [expr for query in queries for expr in (query + ' AND reviewed:true', query)]
        for expression in expressions:
            response = self.client.get("https://rest.uniprot.org/uniprotkb/search", params={
                "query": expression, "format": "json", "size": 2,
                "fields": "accession,gene_names,organism_id",
            }, timeout=(10, 45))
            response.raise_for_status()
            hits = response.json().get("results", [])
            if hits:
                break
        if len(hits) != 1:
            raise ValueError(f"{identifier}: {len(hits)} o más coincidencias; especifica UniProt ID y comprueba el organismo.")
        return hits[0]["primaryAccession"]

    def extracellular_range(self, accession: str) -> tuple:
        response = self.client.get(f'https://rest.uniprot.org/uniprotkb/{accession}.json', timeout=(10,45))
        response.raise_for_status()
        domains = [f for f in response.json().get('features', [])
                   if f.get('type') == 'Topological domain' and f.get('description', '').lower() == 'extracellular']
        if len(domains) != 1:
            raise ValueError('No hay una única región extracelular anotada. Usa estructura completa o un rango explícito.')
        location = domains[0]['location']
        if any(location[end].get('modifier', 'EXACT') != 'EXACT' for end in ('start','end')):
            raise ValueError('Los límites extracelulares son inciertos; selecciona un rango explícito.')
        return int(location['start']['value']), int(location['end']['value'])

    def _fetch_primary(self, identifier: str, local: Optional[str] = None, residue_range=None) -> dict:
        identity = identifier.upper() + (f":{residue_range[0]}-{residue_range[1]}" if residue_range else "")
        key = hashlib.sha256(identity.encode()).hexdigest()[:12]
        target = self.directory / f"{key}.pdb"
        if local:
            source = Path(local).expanduser().resolve()
            validate_pdb(source)
            if source != target.resolve():
                shutil.copyfile(source, target)
            origin, accession = str(source), ""
        else:
            accession = self.resolve(identifier)
            response = self.client.get(f"https://alphafold.ebi.ac.uk/api/prediction/{accession}", timeout=(10, 45))
            response.raise_for_status()
            predictions = response.json()
            # No elegir silenciosamente un fragmento entre varios modelos.
            models = [item for item in predictions if item.get("pdbUrl")]
            # La API puede devolver además isoformas: escoger sólo el accession pedido.
            exact = [item for item in models if item.get("uniprotAccession") == accession]
            if any(item.get("uniprotAccession") for item in models):
                models = exact
            if len(models) != 1:
                raise ValueError(f"{identifier}: {len(models)} modelos; asigna un PDB local para seleccionar la estructura.")
            if residue_range and models[0].get("uniprotStart", 1) != 1:
                raise ValueError("El modelo es un fragmento: revisa su numeración antes de recortar residuos.")
            origin = models[0]["pdbUrl"]
            self._download(origin, target)
        validate_pdb(target)
        metadata = {"source": origin, "uniprot": accession}
        if residue_range:
            start, end = residue_range
            if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end):
                raise ValueError("Rango de residuos inválido.")
            metadata["full_structure_sha256"] = sha256(target)
            lines = target.read_text(encoding="utf-8").splitlines()
            atoms = [line for line in lines if line.startswith("ATOM  ") and start <= int(line[22:26]) <= end]
            if len({line[21] for line in atoms}) != 1 or any(line[26:27].strip() for line in atoms):
                raise ValueError("El recorte exige una sola cadena con numeración de residuos sin inserciones.")
            positions = {int(line[22:26]) for line in atoms}
            if positions != set(range(start, end + 1)):
                raise ValueError("La estructura no cubre completamente el rango solicitado; revisa la numeración.")
            target.write_text("\n".join(atoms + ["TER", "END"]) + "\n", encoding="utf-8")
            validate_pdb(target)
            metadata["residue_range"] = [start, end]
            metadata["preparation"] = "Recorte por numeración PDB; sin alterar coordenadas ni añadir glicanos."
        return {"path": str(target.resolve()), "sha256": sha256(target), **metadata}

    def _wait(self, seconds):
        if self.stop is not None:
            if self.stop.wait(seconds):
                raise InterruptedError('Preparación detenida; se conservó lo completado.')
        else:
            time.sleep(seconds)

    def _request(self, method, url, **kwargs):
        """Tres intentos totales: esperas 2 y 4 s, o Retry-After si es mayor."""
        host = urlsplit(url).hostname
        for attempt in range(3):
            if self.stop is not None and self.stop.is_set():
                raise InterruptedError('Preparación detenida.')
            elapsed = time.monotonic() - self.last_call.get(host, float('-inf'))
            if elapsed < 1:
                self._wait(1-elapsed)
            self.last_call[host] = time.monotonic()
            try:
                response = getattr(self.remote_client, method)(url, allow_redirects=False, **kwargs)
                if 300 <= response.status_code < 400:
                    raise StructureUnavailable('El servicio redirigió la petición; revisar el endpoint.')
                if response.status_code not in (429,500,502,503,504):
                    response.raise_for_status()
                    return response
                response.raise_for_status()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                status = getattr(getattr(exc,'response',None),'status_code',None)
                if status not in (None,429,500,502,503,504) or attempt == 2:
                    raise
                delay = 2 ** (attempt+1)
                header = getattr(getattr(exc,'response',None),'headers',{}).get('Retry-After','')
                if header:
                    try:
                        delay = max(delay,float(header))
                    except ValueError:
                        try:
                            delay = max(delay,(parsedate_to_datetime(header)-datetime.now(timezone.utc)).total_seconds())
                        except (ValueError,TypeError):
                            pass
                self._wait(delay)

    def sequence(self, accession):
        if accession in self.sequences: return self.sequences[accession]
        if REFSEQ.fullmatch(accession) and not ACCESSION.fullmatch(accession):
            response = self._request('get','https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
                params={'db':'protein','id':accession,'rettype':'fasta','retmode':'text','tool':'DockingMatrix'},timeout=(10,60))
        else:
            response = self._request('get',f'https://rest.uniprot.org/uniprotkb/{accession}.fasta',timeout=(10,60))
        lines = response.text.strip().splitlines()
        if not lines or not lines[0].startswith('>') or sum(line.startswith('>') for line in lines) != 1:
            raise StructureUnavailable('La fuente no devolvió una única secuencia FASTA.')
        sequence = ''.join(''.join(lines[1:]).split()).upper()
        if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]+', sequence):
            raise StructureUnavailable('Secuencia vacía o con aminoácidos no estándar; no se modificó silenciosamente.')
        self.sequences[accession]=sequence
        return sequence

    def _fold(self, accession, residue_range):
        from structure_cache import pdb_info
        sequence = self.sequence(accession)
        start, end = residue_range or (1,len(sequence))
        if not 1 <= start <= end <= len(sequence):
            raise ValueError('El rango solicitado queda fuera de la secuencia.')
        selected = sequence[start-1:end]
        if len(selected) > self.esm_max_length:
            raise StructureUnavailable(f'Secuencia de {len(selected)} residuos: supera el límite conservador configurado de {self.esm_max_length} para ESMFold. No se truncó.')
        self.callback({'kind':'message','text':f'{accession}: prediciendo {len(selected)} residuos con ESMFold (servidor remoto)…'})
        response = self._request('post',ESMFOLD_URL,data=selected.encode('ascii'),
                                headers={'Content-Type':'text/plain'},timeout=(10,300))
        target = self.directory/(hashlib.sha256((accession+':'+str(residue_range)+':ESMFold').encode()).hexdigest()[:16]+'.pdb')
        temporary = target.with_suffix('.part')
        try:
            temporary.write_bytes(response.content)
            validate_pdb(temporary)
            info = pdb_info(temporary,'ESMFold',selected)
            if len(info['chains']) != 1:
                raise StructureUnavailable('ESMFold devolvió más de una cadena.')
            # Numerar en coordenadas de la secuencia original, una sola vez.
            output = []
            positions = {}
            for line in temporary.read_text().splitlines():
                if line.startswith(('ATOM  ','HETATM')):
                    key = (line[21],line[22:27])
                    if key not in positions:
                        positions[key] = start + len(positions)
                    if positions[key] > 9999:
                        raise StructureUnavailable('La numeración excede el formato PDB; necesita un modelo manual.')
                    line = line[:22]+f'{positions[key]:4d}'+' '+line[27:]
                output.append(line)
            temporary.write_text('\n'.join(output)+'\n',encoding='utf-8')
            validate_pdb(temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return {'path':str(target.resolve()),'sha256':sha256(target),'source':ESMFOLD_URL,
                'uniprot':accession if ACCESSION.fullmatch(accession) else '',
                'resolved_accession':accession,'structure_source':'ESMFold','structure_status':'FALLBACK_OK',
                'residue_range':list(residue_range) if residue_range else None,
                'numbering_map':{'model_start':1,'original_start':start,'length':len(selected),'pdb_uses_original_numbering':True},
                'input_sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest(),
                'modeled_sequence_sha256':hashlib.sha256(selected.encode()).hexdigest(),
                'remote_pdb_sha256':hashlib.sha256(response.content).hexdigest(),
                'domain_prediction':bool(start != 1 or end != len(sequence)),
                'prediction_method':'ESMFold v1 API; domain isolated' if residue_range else 'ESMFold v1 API; full sequence'}

    def _fetch_legacy(self, identifier: str, local: Optional[str] = None, residue_range=None) -> dict:
        from structure_cache import pdb_info
        if self.stop is not None and self.stop.is_set():
            raise InterruptedError('Preparación detenida.')
        if residue_range and (len(residue_range)!=2 or not all(isinstance(n,int) for n in residue_range) or not 1 <= residue_range[0] <= residue_range[1]):
            raise ValueError('Rango de residuos inválido.')
        cached = None if local or not self.use_structure_cache else self.cache.find(identifier,self.taxon,residue_range,self.chains,self.allow_fallback)
        if cached:
            source, metadata = cached
            target = self.directory/('cache_'+sha256(source)[:16]+'.pdb')
            shutil.copyfile(source,target)
            result = {**metadata,'path':str(target.resolve()),'cache_hit':True}
            self.callback({'kind':'message','text':f'{identifier}: Caché válida ({result["structure_source"]})'})
            return result
        try:
            accession = identifier.strip().upper() if local else self.resolve(identifier)
        except (requests.ConnectionError,requests.Timeout,requests.exceptions.RetryError) as exc:
            raise StructureUnavailable('RETRY_PENDING: no se pudo resolver el identificador. '+str(exc)) from exc
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (429,500,502,503,504):
                raise StructureUnavailable('RETRY_PENDING: no se pudo resolver el identificador. '+str(exc)) from exc
            raise
        if not local and accession != identifier.upper():
            cached = self.cache.find(accession,self.taxon,residue_range,self.chains,self.allow_fallback) if self.use_structure_cache else None
            if cached:
                source,metadata=cached
                target=self.directory/('cache_'+sha256(source)[:16]+'.pdb')
                shutil.copyfile(source,target)
                return {**metadata,'path':str(target.resolve()),'cache_hit':True}
        try:
            is_refseq = bool(REFSEQ.fullmatch(accession) and not ACCESSION.fullmatch(accession))
            if is_refseq and not local:
                if not self.allow_fallback:
                    raise StructureUnavailable('RefSeq requiere predicción alternativa; fallback desactivado.')
                result = self._fold(accession,residue_range)
            else:
                try:
                    result = self._fetch_primary(accession,local,residue_range)
                    result.update(structure_source='Local' if local else 'AlphaFold',structure_status='OK',
                                  resolved_accession=accession if not local or ACCESSION.fullmatch(accession) or REFSEQ.fullmatch(accession) else '')
                except requests.HTTPError as exc:
                    if local or exc.response is None or exc.response.status_code != 404 or not self.allow_fallback:
                        raise
                    # Sólo un 404 de la consulta de predicción (no un enlace PDB roto).
                    if not str(exc.response.url).startswith('https://alphafold.ebi.ac.uk/api/prediction/'):
                        raise
                    result = self._fold(accession,residue_range)
        except (requests.ConnectionError,requests.Timeout,requests.exceptions.RetryError) as exc:
            raise StructureUnavailable('RETRY_PENDING: servicio temporalmente inaccesible; no se interpretó como proteína ausente. '+str(exc)) from exc
        except requests.HTTPError as exc:
            code=exc.response.status_code if exc.response is not None else None
            if code in (429,500,502,503,504):
                raise StructureUnavailable('RETRY_PENDING: se agotaron los intentos de consulta. '+str(exc)) from exc
            if code == 400:
                raise ValueError('INPUT_ERROR: el servicio rechazó la entrada (HTTP 400). '+str(exc)) from exc
            raise
        return self._finalize(result,identifier,accession,residue_range)

    def _finalize(self,result,identifier,accession,residue_range):
        from structure_cache import pdb_info
        from provider_settings import METHOD_PROVIDER
        result.setdefault('provider_id',METHOD_PROVIDER.get(result['structure_source'],'local'))
        result.setdefault('prediction_method','PDB seleccionado por el usuario' if result['structure_source']=='Local' else result['structure_source']+'; modelo existente')
        path=Path(result['path'])
        if self.chains:
            selected={c.strip() for c in self.chains.split(',') if c.strip()}
            lines=path.read_text().splitlines()
            available={line[21] for line in lines if line.startswith('ATOM  ')}
            if not selected.issubset(available):
                raise ValueError('Alguna cadena solicitada no existe en el modelo obtenido.')
            path.write_text('\n'.join(line for line in lines if not line.startswith(('ATOM  ','HETATM','TER')) or line[21:22] in selected)+'\n',encoding='utf-8')
        info=pdb_info(path,result['structure_source'])
        result.update({k:v for k,v in info.items() if k!='sequence'})
        result.update(sha256=sha256(path),cache_hit=False,retrieved_at=datetime.now(timezone.utc).isoformat())
        self.cache.store(path,result,identifier,accession,self.taxon,residue_range,self.chains)
        self.callback({'kind':'message','text':f'{identifier}: {result["structure_source"]} OK; pLDDT={result["mean_plddt"]}'})
        return result

    def fetch(self,identifier: str,local: Optional[str]=None,residue_range=None):
        if self.provider_order is None or local:
            return self._fetch_legacy(identifier,local,residue_range)
        from provider_settings import PROVIDERS
        from structure_providers import ProviderMiss, fetch_pdb_repository, fetch_swiss_repository
        order=self.provider_order if self.allow_fallback else ['alphafold']
        if self.stop is not None and self.stop.is_set(): raise InterruptedError('Preparación detenida.')
        if residue_range and (len(residue_range)!=2 or not all(isinstance(n,int) for n in residue_range) or not 1<=residue_range[0]<=residue_range[1]):
            raise ValueError('INPUT_ERROR: rango inválido.')
        cached=self.cache.find(identifier,self.taxon,residue_range,self.chains,True,order) if self.use_structure_cache else None
        if cached:
            return self._use_cached(cached,identifier,order)
        try:
            accession=self.resolve(identifier)
        except requests.RequestException as exc:
            response=getattr(exc,'response',None)
            if isinstance(exc,(requests.ConnectionError,requests.Timeout,requests.exceptions.RetryError)) or (response is not None and response.status_code in (429,500,502,503,504)):
                raise StructureUnavailable('RETRY_PENDING: no se pudo resolver el identificador antes de consultar las estructuras. '+str(exc)) from exc
            raise
        if self.use_structure_cache and accession!=identifier.upper():
            cached=self.cache.find(accession,self.taxon,residue_range,self.chains,True,order)
            if cached: return self._use_cached(cached,identifier,order)
        attempts=[]; transient=False
        for provider in order:
            if self.stop is not None and self.stop.is_set(): raise InterruptedError('Preparación detenida.')
            label=PROVIDERS[provider]
            self.callback({'kind':'message','text':f'{identifier}: consultando {label}…'})
            try:
                if provider in ('alphafold','pdb','swissmodel') and not ACCESSION.fullmatch(accession):
                    raise ProviderMiss('Esta fuente necesita una accession UniProt; se conserva el identificador RefSeq para ESMFold.')
                if provider=='alphafold':
                    result=self._fetch_primary(accession,residue_range=residue_range)
                    result.update(structure_source='AlphaFold',structure_status='OK',resolved_accession=accession)
                elif provider=='pdb': result=fetch_pdb_repository(self,accession,residue_range)
                elif provider=='swissmodel': result=fetch_swiss_repository(self,accession,residue_range)
                else: result=self._fold(accession,residue_range)
                result.update(provider_id=provider,provider_order_used=list(order),provider_attempts=attempts+[{'provider':provider,'status':'OK'}])
                if provider in ('pdb','swissmodel'):
                    result['residue_range']=list(residue_range) if residue_range else None
                result=self._finalize(result,identifier,accession,residue_range)
                return result
            except InterruptedError: raise
            except (requests.RequestException,ValueError,KeyError,RuntimeError) as exc:
                response=getattr(exc,'response',None)
                code=response.status_code if response is not None else None
                temporary=isinstance(exc,(requests.ConnectionError,requests.Timeout,requests.exceptions.RetryError)) or code in (429,500,502,503,504)
                transient=transient or temporary
                attempts.append({'provider':provider,'status':'RETRY_PENDING' if temporary else 'NO_USABLE_MODEL','detail':str(exc)})
                self.callback({'kind':'message','text':f'{label}: {attempts[-1]["status"]}: {exc}'})
                if code==400 or str(exc).startswith('INPUT_ERROR:'):
                    raise ValueError('INPUT_ERROR: '+str(exc)) from exc
                if temporary and not self.continue_provider_errors:
                    pending=StructureUnavailable('RETRY_PENDING: '+str(exc))
                    pending.provider_attempts=attempts
                    raise pending from exc
        error=StructureUnavailable(('RETRY_PENDING: ' if transient else '')+'Ningún proveedor habilitado pudo obtener una estructura válida. '+' | '.join(a['provider']+': '+a['detail'] for a in attempts))
        error.provider_attempts=attempts
        raise error

    def _use_cached(self,cached,identifier,order):
        source,metadata=cached
        target=self.directory/('cache_'+sha256(source)[:16]+'.pdb')
        shutil.copyfile(source,target)
        result={**metadata,'path':str(target.resolve()),'cache_hit':True,'provider_order_used':list(order)}
        from provider_settings import METHOD_PROVIDER
        provider=result.get('provider_id',METHOD_PROVIDER.get(result['structure_source'],'unknown'))
        result['origin_provider_attempts']=metadata.get('provider_attempts',[])
        result['provider_attempts']=[{'provider':provider,'status':'CACHE_HIT'}]
        self.callback({'kind':'message','text':f'{identifier}: Caché válida · {result["structure_source"]}'})
        return result

    def fetch_pdb(self, code: str) -> dict:
        if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", code):
            raise ValueError("Código PDB inválido")
        target = self.directory / f"{code.upper()}.pdb"
        origin = f"https://files.rcsb.org/download/{code.upper()}.pdb"
        self._download(origin, target)
        return {"path": str(target.resolve()), "sha256": sha256(target), "source": origin, "uniprot": "",
                'structure_source':'PDB (RCSB)', 'structure_status':'OK', 'mean_plddt':None,
                'pct_plddt_below_50':None, 'retrieved_at':datetime.now(timezone.utc).isoformat()}

    def _download(self, url: str, target: Path) -> None:
        response = self.client.get(url, timeout=(10, 60))
        response.raise_for_status()
        temporary = target.with_suffix(".part")
        try:
            temporary.write_bytes(response.content)
            validate_pdb(temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
