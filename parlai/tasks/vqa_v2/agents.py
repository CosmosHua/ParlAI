# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from parlai.core.teachers import FixedDialogTeacher
from parlai.core.image_featurizers import ImageLoader
from parlai.tasks.vqa_v1.agents import VQADataset
from .build import build, buildImage

import json
import os


def _path(opt):
    build(opt)
    buildImage(opt)
    dt = opt['datatype'].split(':')[0]

    if dt == 'train':
        ques_suffix = 'v2_OpenEnded_mscoco_train2014'
        annotation_suffix = 'v2_mscoco_train2014'
        img_suffix = os.path.join('train2014', 'COCO_train2014_')
    elif dt == 'valid':
        ques_suffix = 'v2_OpenEnded_mscoco_val2014'
        annotation_suffix = 'v2_mscoco_val2014'
        img_suffix = os.path.join('val2014', 'COCO_val2014_')
    elif dt == 'test':
        ques_suffix = 'v2_OpenEnded_mscoco_test2015'
        annotation_suffix = 'None'
        img_suffix = os.path.join('test2015', 'COCO_test2015_')
    else:
        raise RuntimeError('Not valid datatype.')

    data_path = os.path.join(opt['datapath'], 'VQA-v2',
                             ques_suffix + '_questions.json')

    annotation_path = os.path.join(opt['datapath'], 'VQA-v2',
                                   annotation_suffix + '_annotations.json')

    image_path = os.path.join(opt['datapath'], 'COCO-IMG', img_suffix)

    return data_path, annotation_path, image_path


class DefaultDataset(VQADataset):
    pass


class OeTeacher(FixedDialogTeacher):
    """VQA v2.0 Open-Ended teacher, which loads the json VQA data and
    implements its own `act` method for interacting with student agent.
    agent.
    """
    def __init__(self, opt, shared=None):
        super().__init__(opt)
        data_path, annotation_path, self.image_path = _path(opt)
        self.image_mode = opt.get('image_mode', 'none')

        if shared and 'ques' in shared:
            self.ques = shared['ques']
            if 'annotation' in shared:
                self.annotation = shared['annotation']
            self.image_loader = shared['image_loader']
        else:
            self._setup_data(data_path, annotation_path)
            self.image_loader = ImageLoader(opt)

        self.reset()

    def reset(self):
        super().reset()
        self.example = None
        # call this once to get the cache moving
        self.next_example()

    def num_examples(self):
        return len(self.ques['questions'])

    def num_episodes(self):
        return self.num_examples()

    def submit_load_request(self, image_id):
        img_path = self.image_path + '%012d.jpg' % (image_id)
        self.data_loader.request_load(self.receive_data, self.image_loader.load, (img_path,))

    def get(self, episode_idx, entry_idx=0):
        # queue up the next one
        qa = self.ques['questions'][episode_idx]
        question = qa['question']

        action = {
            'text': question,
            'image_id': qa['image_id'],
            'episode_done': True
        }

        if not self.datatype.startswith('test'):
            anno = self.annotation['annotations'][episode_idx]
            action['labels'] = [ans['answer'] for ans in anno['answers']]

        return action

    def next_example(self):
        # save the currently queued example
        ready = None
        if self.example is not None:
            if self.image_mode != 'none':
                image = self.data_queue.get()
                self.example['image'] = image
            ready = (self.example, self.epochDone)
        # queue up the next example
        self.example, self.epochDone = super().next_example()
        if self.image_mode != 'none' and 'image_id' in self.example:
            image_id = self.example['image_id']
            self.submit_load_request(image_id)
        return ready

    def share(self):
        shared = super().share()
        shared['ques'] = self.ques
        if hasattr(self, 'annotation'):
            shared['annotation'] = self.annotation
        shared['image_loader'] = self.image_loader
        return shared

    def _setup_data(self, data_path, annotation_path):
        print('loading: ' + data_path)
        with open(data_path) as data_file:
            self.ques = json.load(data_file)

        if not self.datatype.startswith('test'):
            print('loading: ' + annotation_path)
            with open(annotation_path) as data_file:
                self.annotation = json.load(data_file)


class AllTeacher(OeTeacher):
    """
    VQA v2.0 Open-Ended teacher, which inherits from OeTeacher and
    gives access to the multiple choice answer.
    """

    def act(self):
        episode_idx = self.episode_idx
        action = super().act()

        if not self.datatype.startswith('test'):
            anno = self.annotation['annotations'][self.episode_idx]
            self.mclabel = [anno['multiple_choice_answer']]

        if self.datatype.startswith('train'):
            action['mc_label'] = self.mclabel

        return action


class DefaultTeacher(OeTeacher):
    pass
