"""Bounded reuse within one analysis. RAM only; cleared even after failure."""
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
_CURRENT=ContextVar('cleanqa_run',default=None)

def analysis_scope(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if _CURRENT.get() is not None:return fn(*args,**kwargs)
        memory=OrderedDict();token=_CURRENT.set(memory)
        try:return fn(*args,**kwargs)
        finally:memory.clear();_CURRENT.reset(token)
    return wrapped

def within_run(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        memory=_CURRENT.get()
        if memory is None:return fn(*args,**kwargs)
        key=(fn.__module__,fn.__name__,args,tuple(sorted(kwargs.items())))
        if key in memory:
            memory.move_to_end(key);return memory[key]
        value=fn(*args,**kwargs);memory[key]=value
        if len(memory)>20000:memory.popitem(last=False)
        return value
    return wrapped

class RunDictionary:
    """No changes to dictionary vocabulary; exact-case lookups scoped to one run."""
    def __init__(self,dictionary):self.dictionary=dictionary;self.lookups=OrderedDict()
    def lookup(self,word):
        if word in self.lookups:
            self.lookups.move_to_end(word);return self.lookups[word]
        value=self.dictionary.lookup(word);self.lookups[word]=value
        if len(self.lookups)>20000:self.lookups.popitem(last=False)
        return value
    def __getattr__(self,name):return getattr(self.dictionary,name)
