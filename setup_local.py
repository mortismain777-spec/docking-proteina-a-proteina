"""Descarga oficial separada del motor; no se redistribuyen sus ejecutables."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from data_fetcher import session
from local_engine import LocalEngine

ROOT=Path(__file__).resolve().parent
SOURCE='https://raw.githubusercontent.com/huang-laboratory/HDOCKlite/main/'


def setup(download=False, license_reviewed=False, distribution=''):
    directory=ROOT/'tools/hdocklite'
    directory.mkdir(parents=True,exist_ok=True)
    if download:
        if not license_reviewed:
            raise ValueError('Lee https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt y confirma que tu uso está autorizado mediante --license-reviewed.')
        client=session(); manifest={}
        for name in ('LICENSE.txt','README','hdock','createpl'):
            response=client.get(SOURCE+name,timeout=(10,120))
            response.raise_for_status()
            path=directory/name
            path.write_bytes(response.content)
            manifest[name]={'url':SOURCE+name,'sha256':hashlib.sha256(response.content).hexdigest()}
            print('Descargado:',name,flush=True)
        (directory/'installation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for name in ('hdock','createpl'):
        if not (directory/name).exists():
            raise ValueError('Falta el motor. Descárgalo con --download --license-reviewed tras revisar su licencia.')
    engine=LocalEngine(str(directory),distribution)
    if os.name=='nt':
        command=engine.prefix()+['chmod','+x',engine.path(directory/'hdock'),engine.path(directory/'createpl')]
        subprocess.run(command,check=True,timeout=30)
    else:
        for name in ('hdock','createpl'):
            (directory/name).chmod((directory/name).stat().st_mode | 0o111)
    print('Motor verificado:',engine.check())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--license-reviewed',action='store_true')
    parser.add_argument('--distribution',default='')
    args=parser.parse_args()
    try:
        setup(args.download,args.license_reviewed,args.distribution)
    except Exception as exc:
        parser.exit(1,str(exc)+'\n')
