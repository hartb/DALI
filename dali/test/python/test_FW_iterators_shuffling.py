# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function, division
import math
from nvidia.dali.pipeline import Pipeline
import nvidia.dali.ops as ops
from nvidia.dali.plugin.mxnet import DALIGenericIterator as MXNetIterator
from nvidia.dali.plugin.pytorch import DALIGenericIterator as PyTorchIterator
import torch
import mxnet
import numpy as np
import os

class COCOReaderPipeline(Pipeline):
    def __init__(self, data_paths, batch_size, num_threads, shard_id, num_gpus, random_shuffle, stick_to_shard, shuffle_after_epoch, pad_last_batch, initial_fill=1024):
        # use only 1 GPU, as we care only about shard_id
        super(COCOReaderPipeline, self).__init__(batch_size, num_threads, 0, prefetch_queue_depth=1)
        self.input = ops.COCOReader(file_root = data_paths[0], annotations_file=data_paths[1],
                                    shard_id = shard_id, num_shards = num_gpus, random_shuffle=random_shuffle,
                                    save_img_ids=True, stick_to_shard=stick_to_shard,shuffle_after_epoch=shuffle_after_epoch,
                                    pad_last_batch=pad_last_batch, initial_fill=initial_fill)

    def define_graph(self):
        images, bb, labels, ids = self.input(name="Reader")
        return ids

test_data_root = os.environ['DALI_EXTRA_PATH']
coco_folder = os.path.join(test_data_root, 'db', 'coco')
data_sets = [[os.path.join(coco_folder, 'images'), os.path.join(coco_folder, 'instances.json')]]


def gather_ids(dali_train_iter, data_getter, pad_getter, data_size):
    img_ids_list = []
    batch_size = dali_train_iter.batch_size
    pad = 0
    for it in iter(dali_train_iter):
        tmp = data_getter(it[0]).copy()
        pad += pad_getter(it[0])
        img_ids_list.append(tmp)
    img_ids_list = np.concatenate(img_ids_list)
    img_ids_list_set = set(img_ids_list)

    remainder = int(math.ceil(data_size / batch_size)) * batch_size - data_size
    mirrored_data = img_ids_list[-remainder - 1:]

    return img_ids_list, img_ids_list_set, mirrored_data, pad, remainder


def create_pipeline(creator, batch_size, num_gpus):
    iters = 0
    #make sure that data size and batch are not divisible
    while iters % batch_size == 0:
        while iters != 0 and iters % batch_size == 0:
            batch_size += 1

        pipes = [creator(gpu) for gpu in range(num_gpus)]
        [pipe.build() for pipe in pipes]
        iters = pipes[0].epoch_size("Reader")
        iters = iters // num_gpus
    return pipes, iters


def test_mxnet_iterator_last_batch_no_pad_last_batch():
    num_gpus = 1
    batch_size = 100

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                  data_paths=data_sets[0], random_shuffle=True, stick_to_shard=False,
                                                                  shuffle_after_epoch=False, pad_last_batch=False), batch_size, num_gpus)

    dali_train_iter = MXNetIterator(pipes, [("ids", MXNetIterator.DATA_TAG)],
                                    size=pipes[0].epoch_size("Reader"), fill_last_batch=True)

    img_ids_list, img_ids_list_set, mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x.data[0].squeeze().asnumpy(), lambda x: x.pad, data_size)

    assert len(img_ids_list) > data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) != 1


def test_mxnet_iterator_last_batch_pad_last_batch():
    num_gpus = 1
    batch_size = 100
    iters = 0

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                      data_paths=data_sets[0], random_shuffle=True, stick_to_shard=False,
                                                                      shuffle_after_epoch=False, pad_last_batch=True), batch_size, num_gpus)

    dali_train_iter = MXNetIterator(pipes, [("ids", MXNetIterator.DATA_TAG)],
                                    size=pipes[0].epoch_size("Reader"), fill_last_batch=True)

    img_ids_list, img_ids_list_set, mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x.data[0].squeeze().asnumpy(), lambda x: x.pad, data_size)

    assert len(img_ids_list) > data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) == 1

    dali_train_iter.reset()
    next_img_ids_list, next_img_ids_list_set, next_mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x.data[0].squeeze().asnumpy(), lambda x: x.pad, data_size)

    assert len(next_img_ids_list) > data_size
    assert len(next_img_ids_list_set) == data_size
    assert len(set(next_mirrored_data)) == 1


def test_mxnet_iterator_not_fill_last_batch_pad_last_batch():
    num_gpus = 1
    batch_size = 100
    iters = 0

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                      data_paths=data_sets[0], random_shuffle=True, stick_to_shard=False,
                                                                      shuffle_after_epoch=False, pad_last_batch=True), batch_size, num_gpus)

    dali_train_iter = MXNetIterator(pipes, [("ids", MXNetIterator.DATA_TAG)], size=pipes[0].epoch_size("Reader"),
                                    fill_last_batch=False)

    img_ids_list, img_ids_list_set, mirrored_data, pad, remainder = \
        gather_ids(dali_train_iter, lambda x: x.data[0].squeeze().asnumpy(), lambda x: x.pad, data_size)

    assert pad == remainder
    assert len(img_ids_list) - pad == data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) == 1

    dali_train_iter.reset()
    next_img_ids_list, next_img_ids_list_set, next_mirrored_data, pad, remainder = \
        gather_ids(dali_train_iter, lambda x: x.data[0].squeeze().asnumpy(), lambda x: x.pad, data_size)

    assert pad == remainder
    assert len(next_img_ids_list) - pad == data_size
    assert len(next_img_ids_list_set) == data_size
    assert len(set(next_mirrored_data)) == 1


def test_pytorch_iterator_last_batch_no_pad_last_batch():
    num_gpus = 1
    batch_size = 100
    iters = 0

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                      data_paths=data_sets[0], random_shuffle=True, stick_to_shard=False,
                                                                      shuffle_after_epoch=False, pad_last_batch=False), batch_size, num_gpus)

    dali_train_iter = PyTorchIterator(pipes, output_map=["data"], size=pipes[0].epoch_size("Reader"), fill_last_batch=True)

    img_ids_list, img_ids_list_set, mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x["data"].squeeze().numpy(), lambda x: 0, data_size)

    assert len(img_ids_list) > data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) != 1

def test_pytorch_iterator_last_batch_pad_last_batch():
    num_gpus = 1
    batch_size = 100
    iters = 0

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                      data_paths=data_sets[0], random_shuffle=True, stick_to_shard=False,
                                                                      shuffle_after_epoch=False, pad_last_batch=True), batch_size, num_gpus)

    dali_train_iter = PyTorchIterator(pipes, output_map=["data"], size=pipes[0].epoch_size("Reader"), fill_last_batch=True)

    img_ids_list, img_ids_list_set, mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x["data"].squeeze().numpy(), lambda x: 0, data_size)

    assert len(img_ids_list) > data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) == 1

    dali_train_iter.reset()
    next_img_ids_list, next_img_ids_list_set, next_mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x["data"].squeeze().numpy(), lambda x: 0, data_size)

    assert len(next_img_ids_list) > data_size
    assert len(next_img_ids_list_set) == data_size
    assert len(set(next_mirrored_data)) == 1


def test_pytorch_iterator_not_fill_last_batch_pad_last_batch():
    num_gpus = 1
    batch_size = 100
    iters = 0

    pipes, data_size = create_pipeline(lambda gpu: COCOReaderPipeline(batch_size=batch_size, num_threads=4, shard_id=gpu, num_gpus=num_gpus,
                                                                     data_paths=data_sets[0], random_shuffle=False, stick_to_shard=False,
                                                                     shuffle_after_epoch=False, pad_last_batch=True), batch_size, num_gpus)

    dali_train_iter = PyTorchIterator(pipes, output_map=["data"], size=pipes[0].epoch_size("Reader"), fill_last_batch=False, last_batch_padded=True)

    img_ids_list, img_ids_list_set, mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x["data"].squeeze().numpy(), lambda x: 0, data_size)

    assert len(img_ids_list) == data_size
    assert len(img_ids_list_set) == data_size
    assert len(set(mirrored_data)) != 1

    dali_train_iter.reset()
    next_img_ids_list, next_img_ids_list_set, next_mirrored_data, _, _ = \
        gather_ids(dali_train_iter, lambda x: x["data"].squeeze().numpy(), lambda x: 0, data_size)

    # there is no mirroring as data in the output is just cut off,
    # in the mirrored_data there is real data
    assert len(next_img_ids_list) == data_size
    assert len(next_img_ids_list_set) == data_size
    assert len(set(next_mirrored_data)) != 1
