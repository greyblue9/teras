from abc import ABCMeta, abstractmethod
from collections import UserDict
import copy
import re

import numpy as np


class Tokenizer(metaclass=ABCMeta):

    @abstractmethod
    def tokenize(self, document):
        raise NotImplementedError()


class SimpleTokenizer(Tokenizer):

    def tokenize(self, document):
        return document.split()


""" Tokenizer example

from nltk.tokenize import word_tokenize

class NltkTokenizer(Tokenizer)

    def tokenize(self, document):
        return word_tokenize(document)
"""


class Vocab(UserDict):

    def __init__(self):
        super(Vocab, self).__init__()
        self._index = -1
        self._id2word = {}

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def add(self, key):
        return self[key]

    def __missing__(self, key):
        self._index = idx = self._index + 1
        self.data[key] = idx
        self._id2word[idx] = key
        return idx

    def __setitem__(self, key, item):
        if not isinstance(item, int):
            raise ValueError("item must be int, but {} given"
                             .format(type(item)))
        if self._id2word.get(item, key) != key:
            raise ValueError("item has already been assigned "
                             "to another key".format(type(item)))
        if key in self.data:
            del self._id2word[self.data[key]]
        self.data[key] = item
        self._id2word[item] = key
        if item > self._index:
            self._index = item

    def __delitem__(self, key):
        del self._id2word[self.data.pop(key)]

    def copy(self):
        data = self.data
        id2word = self._id2word
        try:
            self.data = {}
            self._id2word = {}
            c = copy.copy(self)
        finally:
            self.data = data
            self._id2word = id2word
        c.update(data)
        return c

    @classmethod
    def fromkeys(cls, iterable):
        self = cls()
        for idx, key in enumerate(iterable):
            self.data[key] = idx
            self._id2word[idx] = key
        self._index = idx
        return self

    def lookup(self, value):
        return self._id2word[value]

    __marker = object()

    def pop(self, key, default=__marker):
        if key in self:
            result = self[key]
            del self[key]
            return result
        if default is self.__marker:
            raise KeyError(key)
        return default

    def popitem(self):
        result = self.data.popitem()
        del self._id2word[result[1]]
        return result

    def clear(self):
        self.data.clear()
        self._id2word.clear()
        self._index = 0

    def update(self, *args, **kwargs):
        for k, v in dict().update(*args, **kwargs):
            self[k] = v

    def setdefault(self, key, default=-1):
        if key in self:
            return self[key]
        self[key] = default
        return default


def normal(scale, dim):
    return np.random.normal(0, scale, dim)


def uniform(scale, dim):
    return np.random.uniform(-1 * scale, 1 * scale, dim)


def lower(x):
    return x


def replace_number(x):
    return re.sub(r'^\d+(,\d+)*(\.\d+)?$', '<NUM>', x.lower())


class Preprocessor:

    def __init__(self,
                 embed_file=None,
                 embed_size=50,
                 unknown="<UNK>",
                 tokenizer=None,
                 initializer=None,
                 preprocess=None):
        self._init_embeddings(embed_file, embed_size)
        self._unknown_id = self._add_vocabulary(unknown, random=False)
        self._pad_id = -1
        if tokenizer:
            self._tokenizer = tokenizer
        else:
            self._tokenizer = SimpleTokenizer()
        if initializer:
            self._initializer = initializer
        else:
            self._initializer = lambda: uniform(1.0, self._embed_size)
        if preprocess:
            self._preprocess_token = preprocess
        else:
            self._preprocess_token = lower

    def set_preprocess_func(self, func):
        self._preprocess_token = func

    def _init_embeddings(self, embed_file, embed_size):
        if embed_file is not None:
            vocab_file = None
            if isinstance(embed_file, (list, tuple)):
                embed_file, vocab_file = embed_file
            vocabulary, embeddings = \
                self._load_embeddings(embed_file, vocab_file)
            embed_size = embeddings.shape[1]
        elif embed_size is not None:
            if embed_size <= 0 or type(embed_size) is not int:
                raise ValueError("embed_size must be a positive integer value")
            vocabulary, embeddings = \
                Vocab(), np.zeros((0, embed_size), np.float32)
        else:
            raise ValueError("embed_file os embed_size must be specified")

        self._vocabulary = vocabulary
        self._embeddings = embeddings
        self._new_embeddings = []
        self._embed_size = embed_size

    @staticmethod
    def _load_embeddings(embed_file, vocab_file=None):
        vocabulary = Vocab()
        embeddings = []
        if vocab_file:
            with open(embed_file) as ef, open(vocab_file) as vf:
                for line1, line2 in zip(ef, vf):
                    word = line2.strip()
                    vector = line1.strip().split(" ")
                    if word not in vocabulary:
                        vocabulary.add(word)
                        embeddings.append(np.array(vector, dtype=np.float32))
        else:
            with open(embed_file) as f:
                lines = f.readlines()
                index = 0
                if len(lines[0].strip().split(" ")) <= 2:
                    index = 1  # skip header
                for line in lines[index:]:
                    cols = line.strip().split(" ")
                    word = cols[0]
                    if word not in vocabulary:
                        vocabulary.add(word)
                        embeddings.append(np.array(cols[1:], dtype=np.float32))
        return vocabulary, np.array(embeddings)

    def _add_vocabulary(self, word, random=True):
        if word in self._vocabulary:
            return self._vocabulary[word]
        index = self._vocabulary[word]
        if random:
            # generate a random embedding for an unknown word
            word_vector = self._initializer()
        else:
            word_vector = np.zeros(self._embed_size, dtype=np.float32)
        self._new_embeddings.append(word_vector)
        return index

    def fit(self, raw_documents, preprocess=True):
        for document in raw_documents:
            self._fit_each(document, preprocess)
        return self

    def _fit_each(self, raw_document, preprocess=True):
        tokens = self._extract_tokens(raw_document, preprocess)
        for token in tokens:
            self._add_vocabulary(token, random=True)
        return self

    def fit_one(self, raw_document, preprocess=True):
        return self._fit_each(raw_document, preprocess)

    def transform(self, raw_documents, length=None, preprocess=True):
        samples = []
        for document in raw_documents:
            samples.append(self._transform_each(document, length, preprocess))
        if length:
            samples = np.array(samples, dtype=np.int32)
        return samples

    def _transform_each(self, raw_document, length=None, preprocess=True):
        tokens = self._extract_tokens(raw_document, preprocess)
        if length is not None:
            if len(tokens) > length:
                raise ValueError(
                    "Token length exceeds the specified length value")
            word_ids = np.full(length, self._pad_id, dtype=np.int32)
        else:
            word_ids = np.zeros(len(tokens), dtype=np.int32)
        for i, token in enumerate(tokens):
            word_ids[i] = self.get_vocabulary_id(token)
        return word_ids

    def transform_one(self, raw_document, length=None, preprocess=True):
        return self._transform_each(raw_document, length, preprocess)

    def _extract_tokens(self, raw_document, preprocess=True):
        if type(raw_document) == list or type(raw_document) == tuple:
            tokens = raw_document
        else:
            tokens = self._tokenizer.tokenize(raw_document)
        if preprocess:
            tokens = [self._preprocess_token(token) for token in tokens]
        return tokens

    def fit_transform(self, raw_documents, length=None, preprocess=True):
        return self \
            .fit(raw_documents) \
            .transform(raw_documents, length, preprocess)

    def fit_transform_one(self, raw_document, length=None, preprocess=True):
        return self \
            ._fit_each(raw_document, preprocess) \
            ._transform_each(raw_document, length, preprocess)

    def pad(self, tokens, length):
        assert type(tokens) == np.ndarray
        pad_size = length - tokens.size
        if pad_size < 0:
            raise ValueError("Token length exceeds the specified length value")
        return np.pad(tokens, (0, pad_size),
                      mode="constant", constant_values=self._pad_id)

    def get_embeddings(self):
        if len(self._new_embeddings) > 0:
            self._embeddings = np.r_[self._embeddings, self._new_embeddings]
            self._new_embeddings = []
        return self._embeddings

    def get_vocabulary_id(self, word):
        return self._vocabulary.get(word, self._unknown_id)

    @property
    def embeddings(self):
        return self.get_embeddings()

    @property
    def unknown_id(self):
        return self._unknown_id

    @property
    def pad_id(self):
        return self._pad_id
