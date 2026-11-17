"""Controlled vectors check cache invalidation, never model quality."""
from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope
from tracecraft.core.store import Store
from tracecraft.echo import Echo


class ConfiguredEncoder:
    model_id='same-model-revision'

    def __init__(self,fingerprint,vector):
        self.fingerprint=fingerprint
        self.vector=vector
        self.calls=0
        self.passage_calls=0

    def encode(self,texts,kind='query'):
        self.calls+=1
        self.passage_calls+=int(kind=='passage')
        return [self.vector for _ in texts]


def test_configuration_change_recomputes_persisted_passage_vectors(tmp_path):
    store=Store(tmp_path/'vectors.sqlite')
    first=Atlas(store,encoder=ConfiguredEncoder('prefix-A',[1.0,0.0]))
    first.search('primary color',Scope(),method='dense',mode='local')
    second=Atlas(store,encoder=ConfiguredEncoder('prefix-B',[0.0,1.0]))
    result=second.search('primary color',Scope(),method='dense',mode='local')
    assert second.encoder.passage_calls>0
    assert all(h.score==1.0 for h in result.hits)


def test_encoder_configuration_invalidates_answer_namespace_and_threshold(tmp_path):
    store=Store(tmp_path/'cache.sqlite')
    first=Echo(store,Atlas(store,encoder=ConfiguredEncoder('pooling-A',[1.0,0.0])))
    assert first.request('primary color',policy='exact')['admitted']
    store.put('cache_config',first.calibration_key(),{'threshold':0.9})
    second=Echo(store,Atlas(store,encoder=ConfiguredEncoder('pooling-B',[1.0,0.0])))
    assert first.namespace(Scope(),'fixture','lexical')!=second.namespace(Scope(),'fixture','lexical')
    assert store.get('cache_config',second.calibration_key()) is None
    assert not second.request('primary color',policy='exact')['hit']
