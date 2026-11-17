"""Standalone CANON experiment; output is reproducible public synthetic evidence."""
import argparse
import json

from tracecraft.atlas import Atlas
from tracecraft.canon import experiment
from tracecraft.core.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=['fixture','local'],default='fixture')
parser.add_argument('--database',default='runtime/canon.sqlite')
args=parser.parse_args()
store=Store(args.database)
print(json.dumps(experiment(store,Atlas(store),mode=args.mode),ensure_ascii=False,indent=2))
