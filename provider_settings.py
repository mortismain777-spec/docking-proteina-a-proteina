"""Política explícita de proveedores gratuitos, guardada por lote."""
PROVIDERS = {
    'alphafold': 'AlphaFold DB · modelo existente',
    'pdb': 'PDB / PDBe · estructura experimental',
    'swissmodel': 'SWISS-MODEL Repository · modelo existente',
    'esmfold': 'ESMFold · nueva predicción remota',
}
DEFAULT_ORDER = ['alphafold','pdb','swissmodel','esmfold']
LEGACY_ORDER = ['alphafold','esmfold']
METHOD_PROVIDER = {'AlphaFold':'alphafold','ESMFold':'esmfold','PDB (PDBe)':'pdb',
                   'PDB (RCSB)':'pdb','SWISS-MODEL Repository':'swissmodel'}


def validate_order(order):
    if not isinstance(order,list) or not order or any(not isinstance(p,str) or p not in PROVIDERS for p in order) or len(set(order)) != len(order):
        raise ValueError('Selecciona al menos un proveedor gratuito conocido, sin duplicados.')
    return list(order)


def policy_from_config(config):
    """Un lote anterior conserva su política hasta que el usuario la cambie."""
    return {'provider_order':validate_order(config.get('provider_order') or LEGACY_ORDER),
            'use_structure_cache':bool(config.get('use_structure_cache',True)),
            'continue_provider_errors':bool(config.get('continue_provider_errors',False))}
