"""Standalone SENTINEL experiment over actual synthetic-corpus outputs."""
import argparse
import json

from tracecraft.atlas import Atlas
from tracecraft.core.store import Store
from tracecraft.sentinel import experiment

parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=['fixture','local'],default='fixture')
parser.add_argument('--database',default='runtime/sentinel.sqlite')
args=parser.parse_args()
store=Store(args.database)
print(json.dumps(experiment(store,Atlas(store),mode=args.mode),ensure_ascii=False,indent=2))
