'''

Aum Sri Sai Ram
Implementation of Affectnet dataset class for OADN : it returns attention maps along with image, label
Authors: Darshan Gera and Dr. S. Balasubramanian, SSSIHL
Date: 16-12-2020
Email: darshangera@sssihl.edu.in
Reference:
1. Mollahosseini, A., Hasani, B. and Mahoor, M.H., 2017. "AffectNet: A database for facial expression, valence,
    and arousal computing in the wild". IEEE Transactions on Affective Computing, 10(1), pp.18-31.
Labels: 0: Neutral, 1: Happiness, 2: Sadness, 3: Surprise, 4: Fear, 5: Disgust, 6: Anger, 7: Contempt, 8: None, 9: Uncertain, 10: No-Face
No of samples in Manually annoated set for each of the class are below:
0:74874 1:134415 2:25459 3:14090 4:6378 5:3803 6:24882 7:3750 
2. For occlusion, pose30 and 45 datasets refer to https://github.com/kaiwang960112/Challenge-condition-FER-dataset based on 
Kai Wang, Xiaojiang Peng, Jianfei Yang, Debin Meng, and Yu Qiao , Shenzhen Institutes of Advanced Technology, Chinese Academy of Sciences
{kai.wang, xj.peng, db.meng, yu.qiao}@siat.ac.cn
"Region Attention Networks for Pose and Occlusion Robust Facial Expression Recognition".
'''

import torch.utils.data as data
from PIL import Image, ImageFile
import os
import pickle
import numpy as np
import matplotlib.image as mpimg
import pandas as pd
import cv2
import matplotlib.pyplot as plt
import torch
from torchvision import transforms
from torchvision.utils import make_grid
ImageFile.LOAD_TRUNCATED_IAMGES = True
import torch.nn.functional as F

import random as rd 
from PIL import ImageDraw
from PIL import ImageFont
import numpy as np
from numpy import linspace
from matplotlib import cm
import math

def PIL_loader(path):
    try:
        with open(path, 'rb') as f:
            return Image.open(f).convert('RGB')
    except IOError:
        print('Cannot load image ' + path)

def switch_expression(expression_argument):
    switcher = {
         0:'neutral',
         1:'Happiness',
          2: 'Sadness',
        3: 'Surprise',
4: 'Fear', 5: 'Disgust', 6: 'Anger',
7: 'Contempt', 8: 'None', 9: 'Uncertain', 10: 'No-Face'
    }
    return switcher.get(expression_argument, 0) #default neutral expression



def convert68to24(landmarks_68 ,input_imgsize, target_imgsize):
    '''
    a) Occlusion Aware Facial Expression Recognition Using CNN With Attention Mechanism
    b)  https://github.com/mysee1989/PG-CNN/blob/master/convert_point/pts68_24

    Out of 68 points : 24 are recomputed along with score as minimum of points considered
    '''
    landmarks_68 = np.transpose(landmarks_68)
    #print(landmarks_68.shape) #np array of size 68x3
   
    landmarks_24 = []

    #16 standard landmark points from eyebrow, eyes, nose and mouth
    single_points = [19, 22, 23, 26, 39, 37, 44, 46, 28, 30, 49, 51, 53, 55, 59, 57] 
    # 2-Point from left eye, 2 from right eye, next left cheek and right cheek = 6 points for averaging
    double_points = [
            [20, 38],
            [25, 45],
            [41, 42],
            [47, 48],
            [18, 59],
            [27, 57]
            ]  
    # 2 more points at offfset from left mouth corner:49 and right mouth corner:55

    
    #First add 16
    for index in single_points:
        landmark = landmarks_68[index-1].reshape(1,3)    
        landmarks_24.append(landmark)
    
    #Add average 6    
    for ele in double_points:
        point1 = landmarks_68[ele[0]-1][:2]
        score1 = landmarks_68[ele[0]-1][2]
        point2 = landmarks_68[ele[1]-1][:2]
        score2 = landmarks_68[ele[1]-1][2]
        midpoint = np.mean(np.array([point1, point2]), axis=0).reshape(1,2)
        score = np.array(min(score1,score2)).reshape(1,1)        
        midpoint_score = np.append(midpoint,score,axis=1).reshape(1,3)
        landmarks_24.append(midpoint_score)

    #add last 2 from mouth corners
    #offset is 16 for 256x256 image, so 
    offset_w =  int((16.0 * input_imgsize[0]) / 256.0) 
    offset_h =  int((16.0 * input_imgsize[1]) / 256.0)
    offset = (offset_w, offset_h)
    # 23rd point: for left mouth offset point     
    left_mouth_corner_point = landmarks_68[49-1,:2] 
    left_mouth_corner_offset_point = left_mouth_corner_point - offset
    left_mouth_corner_offset_point_score = landmarks_68[49-1,2].reshape(1,1)    
    left_mouth_corner_new = np.append(left_mouth_corner_offset_point.reshape(1,2),left_mouth_corner_offset_point_score,axis=1).reshape(1,3)
    right_mouth_corner_point = landmarks_68[55-1,:2]
    right_mouth_corner_offset_point = np.array([right_mouth_corner_point[0]-offset[0], right_mouth_corner_point[1]+offset[1]])
    right_mouth_corner_offset_point_score = landmarks_68[55-1,2].reshape(1,1)
    right_mouth_corner_new = np.append(right_mouth_corner_offset_point.reshape(1,2),right_mouth_corner_offset_point_score,axis=1).reshape(1,3)    
    #[IMP: this 4 for 23rd and 24th point is chosen depending on size of image. for 256x256 size image it was 16]
    # 24th point: for right mouth offset point
    landmarks_24.append(left_mouth_corner_new)
    landmarks_24.append(right_mouth_corner_new)    
    landmarks_24_scaled = [ [landmarks_24[i][0,0] * target_imgsize[0]  / input_imgsize[0], landmarks_24[i][0,1] * target_imgsize[1]  / input_imgsize[1], landmarks_24[i][0,2]] for i in range(0, len(landmarks_24))] 
    landmarks_24_scaled = np.asarray(landmarks_24_scaled, np.float32).reshape(24,3)
    return landmarks_24_scaled

def _gaussian(
        size=3, sigma=0.25, amplitude=1, normalize=False, width=None,
        height=None, sigma_horz=None, sigma_vert=None, mean_horz=0.5,
        mean_vert=0.5, score = 1): #score added by DG 

    if width is None:
        width = size
    if height is None:
        height = size
    if sigma_horz is None:
        sigma_horz = sigma
    if sigma_vert is None:
        sigma_vert = sigma
    center_x = mean_horz * width + 0.5
    center_y = mean_vert * height + 0.5
    gauss = np.empty((height, width), dtype=np.float32)
    # generate kernel
    for i in range(height):
        for j in range(width):
            gauss[i][j] = amplitude * math.exp(-(math.pow((j + 1 - center_x) / (
                sigma_horz * width), 2) / 2.0 + math.pow((i + 1 - center_y) / (sigma_vert * height), 2) / 2.0))
    if normalize:
        gauss = gauss / np.sum(gauss)
    return gauss

def draw_gaussian(image, point, sigma, score):
    # Check if the gaussian is inside
    ul = [np.floor(np.floor(point[0]) - 3 * sigma),
          np.floor(np.floor(point[1]) - 3 * sigma)]
    br = [np.floor(np.floor(point[0]) + 3 * sigma),
          np.floor(np.floor(point[1]) + 3 * sigma)]
    if (ul[0] > image.shape[1] or ul[1] >
            image.shape[0] or br[0] < 1 or br[1] < 1):
        return image
    size = 6 * sigma + 1
    g = _gaussian(size)
    g_x = [int(max(1, -ul[0])), int(min(br[0], image.shape[1])) -
           int(max(1, ul[0])) + int(max(1, -ul[0]))]
    g_y = [int(max(1, -ul[1])), int(min(br[1], image.shape[0])) -
           int(max(1, ul[1])) + int(max(1, -ul[1]))]
    img_x = [int(max(1, ul[0])), int(min(br[0], image.shape[1]))]
    img_y = [int(max(1, ul[1])), int(min(br[1], image.shape[0]))]
    assert (g_x[0] > 0 and g_y[1] > 0)
    correct = False
    while not correct:
        try:
            image[img_y[0] - 1:img_y[1], img_x[0] - 1:img_x[1]
            ] = image[img_y[0] - 1:img_y[1], img_x[0] - 1:img_x[1]] + g[g_y[0] - 1:g_y[1], g_x[0] - 1:g_x[1]]
            correct = True
        except:
            print('img_x: {}, img_y: {}, g_x:{}, g_y:{}, point:{}, g_shape:{}, ul:{}, br:{}'.format(img_x, img_y, g_x, g_y, point, g.shape, ul, br))
            ul = [np.floor(np.floor(point[0]) - 3 * sigma),
                np.floor(np.floor(point[1]) - 3 * sigma)]
            br = [np.floor(np.floor(point[0]) + 3 * sigma),
                np.floor(np.floor(point[1]) + 3 * sigma)]
            g_x = [int(max(1, -ul[0])), int(min(br[0], image.shape[1])) -
                int(max(1, ul[0])) + int(max(1, -ul[0]))]
            g_y = [int(max(1, -ul[1])), int(min(br[1], image.shape[0])) -
                int(max(1, ul[1])) + int(max(1, -ul[1]))]
            img_x = [int(max(1, ul[0])), int(min(br[0], image.shape[1]))]
            img_y = [int(max(1, ul[1])), int(min(br[1], image.shape[0]))]
            pass
    image[image > 1] = 1
    return image
    
    
def get_class(idx):
        classes = {
            0: 'Neutral',
            1: 'Happy',
            2: 'Sad',
            3: 'Surprise',
            4: 'Fear',
            5: 'Disgust',
            6: 'Anger',
            7: 'Contempt'}

        return classes[idx]
    
def default_reader(fileList, landmarksfile, num_classes = 7 , target_imgsize = 224):
    imgList = []
    if fileList.find('validation.csv')>-1: #hardcoded for Affectnet dataset
       start_index = 0
       max_samples = 100000
    else:
       start_index = 1
       max_samples = 500000
       
       
    with open(landmarksfile,'rb') as fp:
        landmarks_dict = pickle.load(fp)
    num_per_cls_dict = dict()
    for i in range(0, num_classes):
        num_per_cls_dict[i] = 0

    if num_classes == 7:
       exclude_list = [7, 8,9,10]
    else:
       exclude_list = [8,9,10]

    expression_0 = 0
    expression_1 = 0
    expression_2 = 0
    expression_3 = 0
    expression_4 = 0
    expression_5 = 0
    expression_6 = 0
    expression_7 = 0

    '''
    Below Ist two options for occlusion and pose case and 3rd one for general
    '''
    f = open('../data/Affectnetmetadata/validation.csv','r')
    lines = f.readlines()

    #random.shuffle(lines) #random shuffle to get random 5000 images

    if fileList.find('occlusion') > -1:
       fp = open(fileList,'r')
       for names in fp.readlines():
           _, target, image_path,_  = names.split('/') 
           image_path = image_path.strip()           
           for line in lines:
               if line.find(image_path)>-1:
                  
                  imgPath  = line.strip().split(',')[0] #folder/imagename
                  (x,y,w,h)  = line.strip().split(',')[1:5]#bounding box coordinates
                  expression = int(line.strip().split(',')[6])  
                  if landmarks_dict.get((imgPath.split('/')[-1]).strip(),None) is None:
                     continue
                  else:
                     landmarks_68 = landmarks_dict[(imgPath.split('/')[-1]).strip()]                              
                  if expression not in exclude_list: #Adding only list of first 8 expressions 
                     imgList.append([imgPath, expression, landmarks_68])
                     num_per_cls_dict[expression] = num_per_cls_dict[expression] + 1                     
       fp.close()
       return imgList, num_per_cls_dict 
    elif fileList.find('pose') > -1:
       fp = open(fileList,'r')
       for names in fp.readlines():
           target, image_path  = names.split('/')
           image_path = image_path.strip()  
           for line in lines:
               if line.find(image_path) > -1:                  
                  imgPath  = line.strip().split(',')[0] #folder/imagename
                  (x,y,w,h)  = line.strip().split(',')[1:5]#bounding box coordinates            
                  expression = int(line.strip().split(',')[6])  
                  if landmarks_dict.get(imgPath.split('/')[-1],None) is None:
                     continue
                  else:
                     landmarks_68 = landmarks_dict[imgPath.split('/')[-1]]            
                  if expression not in exclude_list: #Adding only list of first 8 expressions 
                     imgList.append([imgPath, expression, landmarks_68])
                     num_per_cls_dict[expression] = num_per_cls_dict[expression] + 1
        
       fp.close()
       return imgList, num_per_cls_dict 
    
             
    else:   #training or validation

        fp = open(fileList, 'r')
        for line in fp.readlines()[start_index:]:  #Ist line is header for automated labeled images
            
            imgPath  = line.strip().split(',')[0] #folder/imagename
            (x,y,w,h)  = line.strip().split(',')[1:5]#bounding box coordinates
            x,y,w,h = int(x),int(y),int(w),int(h)
            expression = int(line.strip().split(',')[6])#emotion label

            if landmarks_dict.get(imgPath.split('/')[-1],None) is None:
                     continue
            else:
                     landmarks_68 = landmarks_dict[imgPath.split('/')[-1]]
            
            
            if expression == 0:
               expression_0 = expression_0 + 1            
               if expression_0 > max_samples:
                  continue
  
            if expression == 1:
               expression_1 = expression_1 + 1
               if expression_1 > max_samples:
                  continue  

            if expression == 2:
               expression_2 = expression_2 + 1
               if expression_2 > max_samples:
                  continue  

            if expression == 3:
               expression_3 = expression_3 + 1
               if expression_3 > max_samples:
                  continue  

            if expression == 4:
               expression_4 = expression_4 + 1
               if expression_4 > max_samples:
                  continue  

            if expression == 5:
               expression_5 = expression_5 + 1
               if expression_5 > max_samples:
                  continue  

            if expression == 6:
               expression_6 = expression_6 + 1
               if expression_6 > max_samples:
                  continue  

            if expression == 7:
               expression_7 = expression_7 + 1
               if expression_7 > max_samples:
                  continue  

            if expression not in exclude_list: #Adding only list of first 8 expressions 
               imgList.append([imgPath, expression, landmarks_68])#landmarks_list])
               num_per_cls_dict[expression] = num_per_cls_dict[expression] + 1 
        fp.close()
        print('Total included ', len(imgList), num_per_cls_dict)
        return imgList,num_per_cls_dict


class ImageList(data.Dataset):
    def __init__(self, root, fileList, landmarksfile='../data/Affectnetmetadata/affectnet_landmarks_scores.pkl', num_classes=8, 
                                target_imgsize = 28, transform = None, list_reader = default_reader, loader=PIL_loader):
        self.root = root
        self.cls_num = num_classes
        
        self.imgList, self.num_per_cls_dict =  list_reader(fileList=fileList, landmarksfile = landmarksfile, num_classes= num_classes,  target_imgsize = target_imgsize )
        self.transform = transform
        self.loader = loader
        self.fileList  = fileList
        self.score_threshold = 0.6        
        self.target_imgsize = target_imgsize
        self.input_imgsize = 224 #Not fixed , it changes from image to image
        self.is_save =  False
        
    def generate_gaussian_attention_maps(self, image, landmarks_24, input_imgsize, threshold): #target_image size not required here as attention map size will be that of input image size

        assert isinstance(image, Image.Image), 'image type is not PIL.Image.Image'
        _image = np.array(image.convert('L'))
       
    
        attention_map = np.zeros_like(_image, np.float32)
        final_attention_gaussian_maps = []
        pts =  landmarks_24.copy()
        num_points = len(pts)#.shape[1]
        visiable_points = []
        for idx in range(num_points):
            if pts[idx][2] > threshold: #checking score is greater than threshold
                visiable_points.append( True )
            else:
                visiable_points.append( False )
        visiable_points = np.array( visiable_points )
        #print (' points with score > threshold : {}'.format( np.sum(visiable_points) ))
        for idx in range(num_points):
            attention_map = np.zeros_like(_image, np.float32)
            if visiable_points[ idx ]:
               point = (pts[idx][0], pts[idx][1])
               score = pts[idx][2]
               attention_map = draw_gaussian(attention_map, point, sigma = 7, score = score )   #Sigma            
            final_attention_gaussian_maps.append(attention_map)

            if self.is_save:
               attention_gaussian_map = Image.fromarray(np.uint8(255 * attention_map))
               attention_gaussian_map.save( str(idx)+'_attention_map.jpg')
        
        return np.array(final_attention_gaussian_maps)
    def __getitem__(self, index):       
        imgPath, target_expression,landmarks_68 = self.imgList[index]
        
            
        img = self.loader(os.path.join(self.root, imgPath))       
        
        self.input_imgsize = img.size[0]        
        
        landmarks = convert68to24(landmarks_68 ,img.size[0:2], target_imgsize=(28,28))
            
        landmarks_24 = [(int(landmarks[i][0]),int(landmarks[i][1]), landmarks[i][2]) for i in range(0,24)]
        
        #attention_map size will be that of input imagesize
        attention_maps = self.generate_gaussian_attention_maps(img, landmarks_24, self.input_imgsize, self.score_threshold)
        attention_maps = torch.from_numpy(attention_maps).unsqueeze(0)
        
        face = img#.crop(area) 
        
        if self.transform is not None:
            face = self.transform(face)
        
        attention_maps = F.interpolate(attention_maps,(14,14), mode='bilinear', align_corners =  False)
        
        return  face, target_expression, attention_maps
        

    def __len__(self):
        return len(self.imgList)

    def get_cls_num_list(self):
        cls_num_list = []
        for i in range(self.cls_num):
            cls_num_list.append(self.num_per_cls_dict[i])
        return cls_num_list


if __name__=='__main__':
   
    rootfolder= '../data/AffectNetdataset/Manually_Annotated_Images_aligned/'
   filename = '../data/Affectnetmetadata/training.csv'

   imagesize =  224
   transform = transforms.Compose([transforms.Resize((imagesize,imagesize)), transforms.ToTensor()])
   
   dataset = ImageList(root=rootfolder, fileList = filename,  landmarksfile = '../data/Affectnetmetadata/training_affectnet_landmarks_scores.pkl', transform = transform     )

   fdi = iter(dataset)
   for i, data in enumerate(fdi):
        if i < 2:
           print('loading ',i,  data[0].size(),data[1], data[2].size())
        else:
           break


