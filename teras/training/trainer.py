import math

from .. import logging as Log
from ..base.event import Callback, Event, EventSender
from ..dataset import Dataset
from ..utils.progressbar import ProgressBar


class TrainEvent(Event):
    TRAIN_BEGIN = 'train_begin'
    TRAIN_END = 'train_end'
    EPOCH_BEGIN = 'epoch_begin'
    EPOCH_END = 'epoch_end'
    EPOCH_TRAIN_BEGIN = 'epoch_train_begin'
    EPOCH_TRAIN_END = 'epoch_train_end'
    EPOCH_VALIDATE_BEGIN = 'epoch_validate_begin'
    EPOCH_VALIDATE_END = 'epoch_validate_end'
    BATCH_BEGIN = 'batch_begin'
    BATCH_END = 'batch_end'


class ProgressCallback(Callback):

    def __init__(self, name="progress_callback", **kwargs):
        super(ProgressCallback, self).__init__(name, **kwargs)
        self._pbar = ProgressBar()
        self.implement(TrainEvent.EPOCH_TRAIN_BEGIN, self.init_progressbar)
        self.implement(TrainEvent.BATCH_BEGIN, self.update_progressbar)
        self.implement(TrainEvent.EPOCH_TRAIN_END, self.finish_progressbar)

    def init_progressbar(self, data):
        self._pbar.start(data['size'])

    def update_progressbar(self, data):
        self._pbar.update((data['batch_size'] * data['batch_index']) + 1)

    def finish_progressbar(self, data):
        self._pbar.finish()


class Reporter(Callback):

    def __init__(self, accuracy_func, name="reporter", **kwargs):
        super(Reporter, self).__init__(name, **kwargs)
        self._acc_func = accuracy_func
        self._logs = {}
        self._history = []

    def get_history(self):
        return self._history

    def on_epoch_train_begin(self, data):
        self._logs = {
            'accuracy': 0.0,
            'loss': 0.0,
        }

    on_epoch_validate_begin = on_epoch_train_begin

    def on_batch_end(self, data):
        accuracy = self._acc_func(data['ys'], data['ts'])
        self._logs['accuracy'] += accuracy

    def on_epoch_train_end(self, data):
        metrics = {
            'accuracy': self._logs['accuracy'] / data['num_batches'],
            'loss': data['loss']
        }
        Log.i("[training] accuracy: {}".format(metrics['accuracy']))
        self._history.append({'training': metrics, 'validation': None})

    def on_epoch_validate_end(self, data):
        metrics = {
            'accuracy': self._logs['accuracy'] / data['num_batches'],
            'loss': data['loss']
        }
        Log.i("[validation] accuracy: {}".format(metrics['accuracy']))
        self._history[-1]['validation'] = metrics


class Trainer(EventSender):
    EventClass = TrainEvent

    def __init__(self, optimizer, model, loss_func, accuracy_func=None):
        super(Trainer, self).__init__()
        self._optimizer = optimizer
        self._model = model
        self._loss_func = loss_func
        self._acc_func = accuracy_func
        self._initialize()

    def _initialize(self):
        def update(optimizer, loss):
            # suppose chainer API
            optimizer.target.cleargrads()
            loss.backward()
            optimizer.update()
        self._update = update

    def configure(self, config):
        if 'update' in config:
            self._config = config['update']
        if 'hooks' in config:
            for event, hook in config['hooks'].items():
                self.add_hook(event, hook)
        if 'callbacks' in config:
            for callback in config['callbacks']:
                self.add_callback(callback)

    def fit(self,
            x,
            y,
            batch_size=32,
            epochs=10,
            validation_data=None,
            verbose=True):

        train_dataset = Dataset(x, y)

        if validation_data:
            do_validation = True
            if len(validation_data) == 2:
                val_x, val_y = validation_data
            else:
                raise ValueError('When passing validation_data, '
                                 'it must contain 2 (x_val, y_val) '
                                 'items, however it contains %d items' %
                                 len(validation_data))
            val_dataset = Dataset(val_x, val_y)
        else:
            do_validation = False

        self._init_events_on_fit(do_validation, verbose)

        forward = (self._model if callable(self._model)
                   else self._model.forward())
        lossfun = self._loss_func

        history = []

        self.notify(TrainEvent.TRAIN_BEGIN)

        for epoch in range(1, epochs + 1):
            epoch_logs = {
                'epoch': epoch,
                'size': train_dataset.size,
            }
            self.notify(TrainEvent.EPOCH_BEGIN, epoch_logs)

            self._process(forward, train_dataset, lossfun,
                          batch_size, epoch_logs)
            if do_validation:
                self._process(forward, val_dataset, lossfun,
                              batch_size, epoch_logs, train=False)

            self.notify(TrainEvent.EPOCH_END, epoch_logs)

        self.notify(TrainEvent.TRAIN_END)

        return history

    def _init_events_on_fit(self, do_validation, verbose=True):
        if verbose:
            callback = ProgressCallback()
            if do_validation:
                callback.implement(TrainEvent.EPOCH_VALIDATE_BEGIN,
                                   callback.init_progressbar)
                callback.implement(TrainEvent.EPOCH_VALIDATE_END,
                                   callback.finish_progressbar)
            self.attach_callback(callback, update=True)

        self.add_hook(TrainEvent.EPOCH_TRAIN_END,
                      lambda data: Log.i(
                          "[training] epoch {} - "
                          "#samples: {}, loss: {}"
                          .format(data['epoch'],
                                  data['size'],
                                  data['loss'])))
        if do_validation:
            self.add_hook(TrainEvent.EPOCH_VALIDATE_END,
                          lambda data: Log.i(
                              "[validation] epoch {} - "
                              "#samples: {}, loss: {}"
                              .format(data['epoch'],
                                      data['size'],
                                      data['loss'])))

        if self._acc_func is not None:
            self.attach_callback(Reporter(self._acc_func))
        self.add_hook(TrainEvent.EPOCH_END, lambda data: Log.v('-'))

    def _process(self,
                 forward,
                 dataset,
                 lossfun,
                 batch_size,
                 logs={}, train=True):
        logs = logs.copy()
        logs['size'] = dataset.size
        num_batches = math.ceil(logs['size'] / batch_size)
        logs['num_batches'] = num_batches
        logs['loss'] = None
        self.notify(TrainEvent.EPOCH_TRAIN_BEGIN
                    if train else TrainEvent.EPOCH_VALIDATE_BEGIN, logs)
        logs['loss'] = 0.0
        for batch_index, batch in enumerate(
                dataset.batch(batch_size, colwise=True, shuffle=train)):
            xs, ts = batch[:-1], batch[-1]
            if len(xs) == 1:
                xs = xs[0]

            batch_logs = {
                'train': train,
                'batch_index': batch_index,
                'batch_size': len(ts),
                'xs': xs,
                'ts': ts,
                'ys': None,
                'loss': None,
            }
            self.notify(TrainEvent.BATCH_BEGIN, batch_logs)

            ys = forward(xs)
            loss = lossfun(ys, ts)

            batch_logs['ys'] = ys
            batch_logs['loss'] = loss
            logs['loss'] += loss

            if train:
                self._update(self._optimizer, loss)
            self.notify(TrainEvent.BATCH_END, batch_logs)
            del loss

        logs['loss'] /= num_batches
        self.notify(TrainEvent.EPOCH_TRAIN_END
                    if train else TrainEvent.EPOCH_VALIDATE_END, logs)