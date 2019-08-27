import _init_path
import argparse
import numpy as np
from pprint import pprint
import os

# about torch
import torch
import torchvision
import torch.nn as nn
from torch.utils.data.sampler import Sampler
from torch.utils.data import DataLoader

# custom module
from model.utils.config import cfg, cfg_from_file, cfg_from_list
from roi_data_layer.roidb import combined_roidb
from roi_data_layer.roibatch_loader import RoibatchLoader
from model.faster_rcnn.vgg16 import vgg16
from model.faster_rcnn.resnet import resnet

###### test ######

##################


class sampler(Sampler):
    '''train_size: 10022, batch_size: 16, train_size/batch_size: 626.375
    '''
    def __init__(self, train_size, batch_size):
        self.num_data = train_size
        self.num_per_batch = int(train_size / batch_size)
        self.batch_size = batch_size
        # self.long() is equivalent to self.to(torch.int64)
        # [[0, 1, 2, ..., batch_size-1]]
        self.range = torch.arange(0, batch_size).view(1, batch_size).long()
        self.leftover_flag = False
        if train_size % batch_size:
            self.leftover = torch.arange(self.num_per_batch * batch_size, train_size).long()
            self.leftover_flag = True

    def __iter__(self):
        rand_num = torch.randperm(self.num_per_batch).view(-1, 1) * self.batch_size
        self.rand_num = rand_num.expand(self.num_per_batch, self.batch_size) + self.range
        self.rand_num_view = self.rand_num.view(-1)
        if self.leftover_flag:
            self.rand_num_view = torch.cat((self.rand_num_view, self.leftover), 0)
        return iter(self.rand_num_view)
    
    def __len__(self):
        return self.num_data

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',
        dest='dataset',
        help='train a dataset',
        default='pascal_voc',
        type=str)
    parser.add_argument('--net',
        dest='net',
        help='vgg16 or resnet101',
        default='vgg16',
        type=str)
    parser.add_argument('--cuda',
        dest='cuda',
        help='whether use CUDA',
        action='store_true')
    parser.add_argument('--save_dir',
        dest='save_dir',
        help='directory to save models',
        default='models',
        type=str)
    parser.add_argument('--batch_size',
        dest='batch_size',
        help='batch_size',
        default=1,
        type=int)
    parser.add_argument('--num_workers',
        help='number of worker to load data',
        default=0,
        type=int)
    parser.add_argument('--class_agnostic',
        dest='class_agnostic',
        help='whether perform class_agnostic bbox regression',
        action='store_true')
    parser.add_argument('--lr',
        dest='lr',
        help='starting learning rate',
        default=0.001,
        type=float)
    parser.add_argument('--lr_decay_step',
        dest='lr_decay_step',
        help='step to do learning rate decay, unit is epoch',
        default=5, type=int)
    parser.add_argument('--lr_decay_gamma',
        dest='lr_decay_gamma',
        help='learning rate decay ratio',
        default=0.1,
        type=float)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()
    
    # config args
    if args.dataset == 'pascal_voc':
        args.imdb_name = 'voc_2007_trainval'
        args.imdbval_name = 'voc_2007_test'
        args.set_cfgs = ['ANCHOR_SCALES', '[8, 16, 32]', 'ANCHOR_RATIOS', '[0.5, 1, 2]', 'MAX_NUM_GT_BOXES', '20']
    
    args.cfg_file = 'cfgs/{}.yml'.format('vgg16')

    if args.cfg_file is not None:
        cfg_from_file(args.cfg_file)
    if args.set_cfgs is not None:
        cfg_from_list(args.set_cfgs)

    print("******** config ********")
    pprint(cfg)
    print('************************')

    np.random.seed(cfg.RNG_SEED)

    if torch.cuda.is_available() and not args.cuda:
        print('WARNING: CUDA is available, run with --cuda')
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    cfg.USE_GPU_NMS = args.cuda

    # imdb and roidb is not same instance
    # example: imdb.num_images -> 5011
    #          len(roidb) -> 10022
    imdb, roidb, ratio_list, ratio_index = combined_roidb(args.imdb_name)
    train_size = len(roidb)

    print('{} roidb entries'.format(train_size))

    # save models dir
    # example: models/vgg16/pascal_voc
    output_dir = args.save_dir + '/' + args.net + '/' + args.dataset
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    sampler_batch = sampler(train_size, args.batch_size)

    dataset = RoibatchLoader(roidb, ratio_list, ratio_index, \
        args.batch_size, imdb.num_classes, training=True)
    
    dataloader = DataLoader(dataset, batch_size=args.batch_size,
                            sampler=sampler_batch, num_workers=args.num_workers)

    if args.cuda:
        cfg.CUDA = True
    
    if args.net == 'vgg16':
        fasterRCNN = vgg16(imdb.classes, pretrained=True, class_agnostic=args.class_agnostic)
    elif args.net == 'res101':
        fasterRCNN = resnet(imdb.classes, 101, pretrained=True, class_agnostic=args.class_agnostic)
    elif args.net == 'res50':
        fasterRCNN = resnet(imdb.classes, 50, pretrained=True, class_agnostic=args.class_agnostic)
    elif args.net == 'res152':
        fasterRCNN = resnet(imdb.classes, 152, pretrained=True, class_agnostic=args.class_agnostic)
    else:
        print('network is not defined')

    fasterRCNN.create_architecture()

    lr = cfg.TRAIN.LEARNING_RATE
    lr = args.lr

    params = []

    ########## test
    print('==========> test')
    for i, v in enumerate(dataloader):
        if i == 0:
            print(v[0].size()) # padding_data
            print(v[1])        # im_info
            print(v[2].size())        # gt_boxes
            print(v[3])        # num_boxes
            break
    # for i, sam in enumerate(sampler_batch):
    #     if i == 0:
    #         print(sam, sam.size())
    #         break
    print('==========> test end')
    ###############