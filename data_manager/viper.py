from __future__ import print_function, absolute_import

import os
import glob
import re
import sys
import urllib
import tarfile
import zipfile
import os.path as osp
from scipy.io import loadmat
import numpy as np
import h5py
from scipy.misc import imsave

from utils.iotools import mkdir_if_missing, write_json, read_json
from .base import BaseImgDataset


class VIPeR(BaseImgDataset):
    """
    VIPeR

    Reference:
    Gray et al. Evaluating appearance models for recognition, reacquisition, and tracking. PETS 2007.

    URL: https://vision.soe.ucsc.edu/node/178
    
    Dataset statistics:
    # identities: 632
    # images: 632 x 2 = 1264
    # cameras: 2
    """
    dataset_dir = 'viper'

    def __init__(self, root='data', split_id=0, verbose=True, use_lmdb=False, **kwargs):
        self.dataset_dir = osp.join(root, self.dataset_dir)
        self.dataset_url = 'http://users.soe.ucsc.edu/~manduchi/VIPeR.v1.0.zip'
        self.cam_a_path = osp.join(self.dataset_dir, 'VIPeR', 'cam_a')
        self.cam_b_path = osp.join(self.dataset_dir, 'VIPeR', 'cam_b')
        self.split_path = osp.join(self.dataset_dir, 'splits.json')

        self._download_data()
        self._check_before_run()
        
        self._prepare_split()
        splits = read_json(self.split_path)
        if split_id >= len(splits):
            raise ValueError("split_id exceeds range, received {}, but expected between 0 and {}".format(split_id, len(splits)-1))
        split = splits[split_id]

        train = split['train']
        query = split['query'] # query and gallery share the same images
        gallery = split['gallery']

        train = [tuple(item) for item in train]
        query = [tuple(item) for item in query]
        gallery = [tuple(item) for item in gallery]
        
        num_train_pids = split['num_train_pids']
        num_query_pids = split['num_query_pids']
        num_gallery_pids = split['num_gallery_pids']
        
        num_train_imgs = len(train)
        num_query_imgs = len(query)
        num_gallery_imgs = len(gallery)

        num_total_pids = num_train_pids + num_query_pids
        num_total_imgs = num_train_imgs + num_query_imgs

        if verbose:
            print("=> VIPeR loaded")
            print("Dataset statistics:")
            print("  ------------------------------")
            print("  subset   | # ids | # images")
            print("  ------------------------------")
            print("  train    | {:5d} | {:8d}".format(num_train_pids, num_train_imgs))
            print("  query    | {:5d} | {:8d}".format(num_query_pids, num_query_imgs))
            print("  gallery  | {:5d} | {:8d}".format(num_gallery_pids, num_gallery_imgs))
            print("  ------------------------------")
            print("  total    | {:5d} | {:8d}".format(num_total_pids, num_total_imgs))
            print("  ------------------------------")

        self.train = train
        self.query = query
        self.gallery = gallery

        self.num_train_pids = num_train_pids
        self.num_query_pids = num_query_pids
        self.num_gallery_pids = num_gallery_pids

        if use_lmdb:
            self.generate_lmdb()

    def _download_data(self):
        if osp.exists(self.dataset_dir):
            print("This dataset has been downloaded.")
            return

        print("Creating directory {}".format(self.dataset_dir))
        mkdir_if_missing(self.dataset_dir)
        fpath = osp.join(self.dataset_dir, osp.basename(self.dataset_url))

        print("Downloading VIPeR dataset")
        urllib.urlretrieve(self.dataset_url, fpath)

        print("Extracting files")
        zip_ref = zipfile.ZipFile(fpath, 'r')
        zip_ref.extractall(self.dataset_dir)
        zip_ref.close()

    def _check_before_run(self):
        """Check if all files are available before going deeper"""
        if not osp.exists(self.dataset_dir):
            raise RuntimeError("'{}' is not available".format(self.dataset_dir))
        if not osp.exists(self.cam_a_path):
            raise RuntimeError("'{}' is not available".format(self.cam_a_path))
        if not osp.exists(self.cam_b_path):
            raise RuntimeError("'{}' is not available".format(self.cam_b_path))

    def _prepare_split(self):
        if not osp.exists(self.split_path):
            print("Creating 10 random splits")

            cam_a_imgs = sorted(glob.glob(osp.join(self.cam_a_path, '*.bmp')))
            cam_b_imgs = sorted(glob.glob(osp.join(self.cam_b_path, '*.bmp')))
            assert len(cam_a_imgs) == len(cam_b_imgs)
            num_pids = len(cam_a_imgs)
            print("Number of identities: {}".format(num_pids))
            num_train_pids = num_pids // 2

            splits = []
            for _ in range(10):
                order = np.arange(num_pids)
                np.random.shuffle(order)
                train_idxs = order[:num_train_pids]
                test_idxs = order[num_train_pids:]
                assert not bool(set(train_idxs) & set(test_idxs)), "Error: train and test overlap"

                train = []
                for pid, idx in enumerate(train_idxs):
                    cam_a_img = cam_a_imgs[idx]
                    cam_b_img = cam_b_imgs[idx]
                    train.append((cam_a_img, pid, 0))
                    train.append((cam_b_img, pid, 1))

                test = []
                for pid, idx in enumerate(test_idxs):
                    cam_a_img = cam_a_imgs[idx]
                    cam_b_img = cam_b_imgs[idx]
                    test.append((cam_a_img, pid, 0))
                    test.append((cam_b_img, pid, 1))

                split = {'train': train, 'query': test, 'gallery': test,
                         'num_train_pids': num_train_pids,
                         'num_query_pids': num_pids - num_train_pids,
                         'num_gallery_pids': num_pids - num_train_pids
                         }
                splits.append(split)

            print("Totally {} splits are created".format(len(splits)))
            write_json(splits, self.split_path)
            print("Split file saved to {}".format(self.split_path))

        print("Splits created")