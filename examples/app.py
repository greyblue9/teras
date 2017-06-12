#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

import chainer
import chainer.functions as F
from progressbar import ProgressBar

from teras.app import App, arg
from teras.dataset import Dataset
from teras.framework.chainer.model import MLP
import teras.logging as Log


# class Resource(object):
#     pass
#
#
# class Trainer(teras.app.Trainer):
#
#     def _process_train(self, data):
#         size = len(train_dataset)
#         batch_count = 0
#         loss = 0.0
#         accuracy = 0.0
#         p = ProgressBar(min_value=0, max_value=size, fd=sys.stderr).start()
#         for batch_index, batch in enumerate(train_dataset.batch(batch_size, colwise=True, shuffle=True)):
#             p.update((batch_size * batch_index) + 1)
#             batch_loss = self.
#         p.finish()
#
#     def _process_test(self, data):
#         size = len(train_dataset)
#         batch_count = 0
#         loss = 0.0
#         accuracy = 0.0
#         p = ProgressBar(min_value=0, max_value=size, fd=sys.stderr).start()
#         for batch_index, batch in enumerate(train_dataset.batch(batch_size, colwise=True, shuffle=True)):
#             p.update((batch_size * batch_index) + 1)
#             batch_loss = self.
#         p.finish()

#
# Resource.load_model()
# Resource.load_data()


# train = Trainer(lazy_loader=Resource)
#


def train(n_epoch=20,
          batch_size=100,
          n_units=512,
          dropout=0.2,
          gpu=-1,
          debug=False):

    # load dataset
    train, test = chainer.datasets.get_mnist()
    train_x, train_y = train._datasets
    test_x, test_y = test._datasets
    train_dataset = Dataset(train_x, train_y)
    test_dataset = Dataset(test_x, test_y)

    Log.v('')
    Log.v("initialize ...")
    Log.v('--------------------------------')
    Log.i('# Minibatch-size: {}'.format(batch_size))
    Log.i('# epoch: {}'.format(n_epoch))
    Log.i('# gpu: {}'.format(gpu))
    Log.i('# model: {}'.format(MLP))
    Log.i('# unit: {}'.format(n_units))
    Log.v('--------------------------------')
    Log.v('')

    # set up a neural network model
    model = MLP([
        MLP.Layer(None, n_units, F.relu, dropout),
        MLP.Layer(None, n_units, F.relu, dropout),
        MLP.Layer(None, 10),
    ])
    if gpu >= 0:
        chainer.cuda.get_device_from_id(gpu).use()
        model.to_gpu()
    chainer.config.use_cudnn = 'auto'
    if debug:
        chainer.config.debug = True
        chainer.config.type_check = True
    else:
        chainer.config.debug = False
        chainer.config.type_check = False

    # set up an optimizer
    optimizer = chainer.optimizers.Adam(
        alpha=0.001, beta1=0.9, beta2=0.999, eps=1e-08)
    optimizer.setup(model)
    Log.i('optimizer: Adam(alpha=0.001, beta1=0.9, beta2=0.999, eps=1e-08)')

    for epoch in range(n_epoch):
        # Training
        chainer.config.train = True
        chainer.config.enable_backprop = True

        size = len(train_dataset)
        batch_count = 0
        loss = 0.0
        accuracy = 0.0

        p = ProgressBar(min_value=0, max_value=size,
                        fd=sys.stderr).start()
        for i, (x, t) in enumerate(
                train_dataset.batch(batch_size, colwise=True, shuffle=True)):
            p.update((batch_size * i) + 1)
            batch_count += 1
            # forward
            y = model(x)
            batch_loss = F.softmax_cross_entropy(y, t)
            batch_accuracy = F.accuracy(y, t)
            loss += batch_loss.data
            accuracy += batch_accuracy.data
            # update
            optimizer.target.zerograds()
            batch_loss.backward()
            optimizer.update()
        p.finish()
        Log.i("[training] epoch %d - #samples: %d, loss: %f, accuracy: %f" %
              (epoch + 1, size, loss / batch_count, accuracy / batch_count))

        # Evaluation
        chainer.config.train = False
        chainer.config.enable_backprop = False

        size = len(test_dataset)
        batch_count = 0
        loss = 0.0
        accuracy = 0.0

        p = ProgressBar(min_value=0, max_value=size,
                        fd=sys.stderr).start()
        for i, (x, t) in enumerate(
                test_dataset.batch(batch_size, colwise=True, shuffle=False)):
            p.update((batch_size * i) + 1)
            batch_count += 1
            # forward
            y = model(x)
            batch_loss = F.softmax_cross_entropy(y, t)
            batch_accuracy = F.accuracy(y, t)
            loss += batch_loss.data
            accuracy += batch_accuracy.data
        p.finish()
        Log.i("[evaluation] epoch %d - #samples: %d, loss: %f, accuracy: %f" %
              (epoch + 1, size, loss / batch_count, accuracy / batch_count))

        Log.v('-')


def decode():
    pass


App.add_command('train', train, {
    'batch_size': arg('--batchsize', '-b', type=int, default=100,
                      help='Number of examples in each mini-batch'),
    'n_epoch': arg('--epoch', '-e', type=int, default=20,
                 help='Number of sweeps over the dataset to train'),
    'gpu': arg('--gpu', '-g', type=int, default=-1),
}, description="execute train")

App.add_command('decode', decode, {})

App.add_arg('debug', True)
App.configure(loglevel=Log.DISABLE)


if __name__ == "__main__":
    App.run()
