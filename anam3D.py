import torch
import torch.nn as nn
import torch.nn.functional as F
import scipy.io as io
import matplotlib.pyplot as plt
import torchvision.transforms as transforms
import numpy as np
from pthflops.ops import count_ops


class Bottleneck(nn.Module):
    def __init__(self,
                 channels,
                 internal_ratio=4,
                 kernel_size=3,
                 padding =1,
                 dilation=1,
                 asymmetric=False,
                 dropout_prob=0,
                 bias=False,
                 relu=True):
        super().__init__()

        # Check in the internal_scale parameter is within the expected range
        # [1, channels]
        if internal_ratio <= 1 or internal_ratio > channels:
            raise RuntimeError("Value out of range. Expected value in the "
                               "interval [1, {0}], got internal_scale={1}."
                               .format(channels, internal_ratio))

        internal_channels = channels // internal_ratio

        if relu:
            activation = nn.ReLU
        else:
            activation = nn.PReLU

        # Main branch - shortcut connection

        # 1x1 projection convolution
        self.ext_conv1 = nn.Sequential(
            nn.Conv3d(
                channels,
                internal_channels,
                kernel_size=1,
                stride=1,
                bias=bias), nn.BatchNorm3d(internal_channels), activation())


        self.ext_conv2 = nn.Sequential(
             nn.Conv3d(
                internal_channels,
                internal_channels,
                kernel_size=kernel_size,
                stride=1,
                padding=padding,
                dilation=dilation,
                bias=bias), nn.BatchNorm3d(internal_channels), activation())

        # 1x1 expansion convolution
        self.ext_conv3 = nn.Sequential(
            nn.Conv3d(
                internal_channels,
                channels,
                kernel_size=1,
                stride=1,
                bias=bias), nn.BatchNorm3d(channels), activation())

        self.ext_regul = nn.Dropout3d(p=dropout_prob)
        # PReLU layer to apply after adding the branches
        self.out_activation = activation()

    def forward(self, x):
        # Main branch shortcut
        main = x
        # Extension branch
        ext = self.ext_conv1(x)
        ext = self.ext_conv2(ext)
        ext = self.ext_conv3(ext)
        ext = self.ext_regul(ext)
        # Add main and extension branches
        out = main + ext
        return self.out_activation(out)

class AnamNet(nn.Module):

    def __init__(self):

        super(AnamNet, self).__init__()

        # Conv block 1 - Down 1
        self.conv1_block = nn.Sequential(
            nn.Conv3d(in_channels=1, out_channels=32,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(32),
            nn.LeakyReLU(0.1),
            )
        self.max1 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 1
        self.bottleneck1 = Bottleneck(32)


        # Conv block 2 - Down 2
        self.conv2_block = nn.Sequential(
            nn.Conv3d(in_channels=32, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )
        self.max2 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 2
        self.bottleneck2 = Bottleneck(64)

        # Conv block 3 - Down 3
        self.conv3_block = nn.Sequential(
            nn.Conv3d(in_channels=64, out_channels=128,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(128),
            nn.LeakyReLU(0.1),
        )
        self.max3 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 3
        self.bottleneck3 = Bottleneck(128)

        # Conv block 4 - Down 4
        self.conv4_block = nn.Sequential(
            nn.Conv3d(in_channels=128, out_channels=128,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(128),
            nn.LeakyReLU(0.1),
        )
        self.max4 = nn.MaxPool3d(kernel_size=2, stride=2)

        # Up 1
        self.up_1 = nn.ConvTranspose3d(in_channels=128, out_channels=128, kernel_size=2, stride=2)

        self.bottleneck4 = Bottleneck(128)
        # Up Conv block 1
        self.conv_up_1 = nn.Sequential(
            nn.Conv3d(in_channels=256, out_channels=128,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(128),
            nn.LeakyReLU(0.1),
        )

        # Up 2
        self.up_2 = nn.ConvTranspose3d(in_channels=128, out_channels=128, kernel_size=2, stride=2)
        
        self.bottleneck5 =Bottleneck(128)  
        # Up Conv block 2
        self.conv_up_2 = nn.Sequential(
            nn.Conv3d(in_channels=256, out_channels=128,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(128),
            nn.LeakyReLU(0.1),
        )

        # Up 3
        self.up_3 = nn.ConvTranspose3d(in_channels=128, out_channels=64, kernel_size=2, stride=2)

        self.bottleneck6 =   Bottleneck(64)
        # Up Conv block 3
        self.conv_up_3 = nn.Sequential(
            nn.Conv3d(in_channels=128, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )

        # Up 4
        self.up_4 = nn.ConvTranspose3d(in_channels=64, out_channels=32, kernel_size=2, stride=2)

        # Up Conv block 4
        self.conv_up_4 = nn.Sequential(
            nn.Conv3d(in_channels=64, out_channels=32,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(32),
            nn.LeakyReLU(0.1),
        )

        # Final output
        self.conv_final = nn.Conv3d(in_channels=32, out_channels=1,
                                    kernel_size=1, padding=0, stride=1)

    def forward(self, x):
        
        #print('inputTensor', x.shape)
        #---------------------------------------------------------------------
        # Down 1
        x = self.conv1_block(x)
        #print('after conv1', x.shape)
        conv1_out = x  # Save out1
        
        x = self.max1(x)
        #print('after pool1', x.shape)
        #--------------------------------------------------------------------
        x = self.bottleneck1(x)
        #print('after bnck1', x.shape)
        # Down 2
        x = self.conv2_block(x)
        #print('after conv2', x.shape)
        conv2_out = x
        
        x = self.max2(x)
        #print('after pool2', x.shape)
        #-------------------------------------------------------------------
        x = self.bottleneck2(x)
        #print('after bnck2', x.shape)
        # Down 3
        x = self.conv3_block(x)
        #print('after conv3', x.shape)
        conv3_out = x
        
        x = self.max3(x)
        #print('after pool3', x.shape)
        #------------------------------------------------------------------
        x = self.bottleneck3(x)
        #print('after bnck3', x.shape)
        # Down 4
        x = self.conv4_block(x)
        #print('after conv4', x.shape)
        conv4_out = x
        
        x = self.max4(x)
        #print('after pool4', x.shape)
        #----------------------------------------------------------------        
        # Up 1
        x = self.up_1(x)
        #print('after  up_1', x.shape)
        x = self.bottleneck4(x)
        #print('after bnck4', x.shape)
        
        x = torch.cat([x, conv4_out], dim=1)
        #print('after cat_1',x.shape)        
        x = self.conv_up_1(x)
        #print('after conv1', x.shape)
        #-----------------------------------------------------------------
        # Up 2
        x = self.up_2(x)
        #print('after  up_2', x.shape)
        x = self.bottleneck5(x)
        #print('after bnck5', x.shape)
        
        x = torch.cat([x, conv3_out], dim=1)
        #print('after cat_2', x.shape)
        x = self.conv_up_2(x)
        #print('after conv2', x.shape)
        #----------------------------------------------------------------
        # Up 3
        x = self.up_3(x)
        #print('after  up_3', x.shape)
        x = self.bottleneck6(x)
        #print('after bnck6', x.shape)
        
        x = torch.cat([x, conv2_out], dim=1)
        #print('after cat_3', x.shape)
        x = self.conv_up_3(x)
        #print('after conv3', x.shape)
        #----------------------------------------------------------------
        # Up 4
        x = self.up_4(x)
        #print('after  up_3', x.shape)
        
        x = torch.cat([x, conv1_out], dim=1)
        #print('after cat_4', x.shape)
        x = self.conv_up_4(x)
        #print('after conv4', x.shape)
        #----------------------------------------------------------------
        # Final output
        x = self.conv_final(x)
        return x

    
        
    def getnumberofparams(self,model,xx):
        pp=0
        for p in (model.parameters()):
            nn=1
            for s in (p.size()):
                nn = nn*s
            pp += nn
        flps, _ = count_ops(model,xx)
        return pp,  (pp*32)/(8*1024*1024), flps
    
    
"""
class AnamNet(nn.Module):

    def __init__(self):

        super(AnamNet, self).__init__()

        # Conv block 1 - Down 1
        self.conv1_block = nn.Sequential(
            nn.Conv3d(in_channels=1, out_channels=16,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(16),
            nn.LeakyReLU(0.1),
            )
        self.max1 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 1
        self.bottleneck1 = Bottleneck(16)


        # Conv block 2 - Down 2
        self.conv2_block = nn.Sequential(
            nn.Conv3d(in_channels=16, out_channels=32,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(32),
            nn.LeakyReLU(0.1),
        )
        self.max2 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 2
        self.bottleneck2 = Bottleneck(32)

        # Conv block 3 - Down 3
        self.conv3_block = nn.Sequential(
            nn.Conv3d(in_channels=32, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )
        self.max3 = nn.MaxPool3d(kernel_size=2, stride=2)
        
        # BottleNeck 3
        self.bottleneck3 = Bottleneck(64)

        # Conv block 4 - Down 4
        self.conv4_block = nn.Sequential(
            nn.Conv3d(in_channels=64, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )
        self.max4 = nn.MaxPool3d(kernel_size=2, stride=2)

        # Up 1
        self.up_1 = nn.ConvTranspose3d(in_channels=64, out_channels=64, kernel_size=2, stride=2)

        self.bottleneck4 = Bottleneck(64)
        # Up Conv block 1
        self.conv_up_1 = nn.Sequential(
            nn.Conv3d(in_channels=128, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )

        # Up 2
        self.up_2 = nn.ConvTranspose3d(in_channels=64, out_channels=64, kernel_size=2, stride=2)
        
        self.bottleneck5 =Bottleneck(64)  
        # Up Conv block 2
        self.conv_up_2 = nn.Sequential(
            nn.Conv3d(in_channels=128, out_channels=64,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(64),
            nn.LeakyReLU(0.1),
        )

        # Up 3
        self.up_3 = nn.ConvTranspose3d(in_channels=64, out_channels=32, kernel_size=2, stride=2)

        self.bottleneck6 =   Bottleneck(32)
        # Up Conv block 3
        self.conv_up_3 = nn.Sequential(
            nn.Conv3d(in_channels=64, out_channels=32,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(32),
            nn.LeakyReLU(0.1),
        )

        # Up 4
        self.up_4 = nn.ConvTranspose3d(in_channels=32, out_channels=16, kernel_size=2, stride=2)

        # Up Conv block 4
        self.conv_up_4 = nn.Sequential(
            nn.Conv3d(in_channels=32, out_channels=16,
                      kernel_size=3, padding=1, stride=1),
            nn.BatchNorm3d(16),
            nn.LeakyReLU(0.1),
        )

        # Final output
        self.conv_final = nn.Conv3d(in_channels=16, out_channels=1,
                                    kernel_size=1, padding=0, stride=1)

    def forward(self, x):
        
        #print('inputTensor', x.shape)
        #---------------------------------------------------------------------
        # Down 1
        x = self.conv1_block(x)
        #print('after conv1', x.shape)
        conv1_out = x  # Save out1
        
        x = self.max1(x)
        #print('after pool1', x.shape)
        #--------------------------------------------------------------------
        x = self.bottleneck1(x)
        #print('after bnck1', x.shape)
        # Down 2
        x = self.conv2_block(x)
        #print('after conv2', x.shape)
        conv2_out = x
        
        x = self.max2(x)
        #print('after pool2', x.shape)
        #-------------------------------------------------------------------
        x = self.bottleneck2(x)
        #print('after bnck2', x.shape)
        # Down 3
        x = self.conv3_block(x)
        #print('after conv3', x.shape)
        conv3_out = x
        
        x = self.max3(x)
        #print('after pool3', x.shape)
        #------------------------------------------------------------------
        x = self.bottleneck3(x)
        #print('after bnck3', x.shape)
        # Down 4
        x = self.conv4_block(x)
        #print('after conv4', x.shape)
        conv4_out = x
        
        x = self.max4(x)
        #print('after pool4', x.shape)
        #----------------------------------------------------------------        
        # Up 1
        x = self.up_1(x)
        #print('after  up_1', x.shape)
        x = self.bottleneck4(x)
        #print('after bnck4', x.shape)
        
        x = torch.cat([x, conv4_out], dim=1)
        #print('after cat_1',x.shape)        
        x = self.conv_up_1(x)
        #print('after conv1', x.shape)
        #-----------------------------------------------------------------
        # Up 2
        x = self.up_2(x)
        #print('after  up_2', x.shape)
        x = self.bottleneck5(x)
        #print('after bnck5', x.shape)
        
        x = torch.cat([x, conv3_out], dim=1)
        #print('after cat_2', x.shape)
        x = self.conv_up_2(x)
        #print('after conv2', x.shape)
        #----------------------------------------------------------------
        # Up 3
        x = self.up_3(x)
        #print('after  up_3', x.shape)
        x = self.bottleneck6(x)
        #print('after bnck6', x.shape)
        
        x = torch.cat([x, conv2_out], dim=1)
        #print('after cat_3', x.shape)
        x = self.conv_up_3(x)
        #print('after conv3', x.shape)
        #----------------------------------------------------------------
        # Up 4
        x = self.up_4(x)
        #print('after  up_3', x.shape)
        
        x = torch.cat([x, conv1_out], dim=1)
        #print('after cat_4', x.shape)
        x = self.conv_up_4(x)
        #print('after conv4', x.shape)
        
        #----------------------------------------------------------------
        # Final output
        x = self.conv_final(x)
        return x

    
        return x

    def getnumberofparams(self,model):
        pp=0
        for p in (model.parameters()):
            nn=1
            for s in (p.size()):
                nn = nn*s
            pp += nn
        return pp,  (pp*32)/(8*1024*1024)

"""

if __name__ == "__main__":
    def tic():
        # Homemade version of matlab tic and toc functions
        import time
        global startTime_for_tictoc
        startTime_for_tictoc = time.time()

    def toc():
        import time
        if 'startTime_for_tictoc' in globals():
            print("Elapsed time is " + str(time.time() - startTime_for_tictoc) + " seconds.")
        else:
            print("Toc: start time not set")
    x= torch.rand(1,1,176, 176, 160)
    tic()
    net=AnamNet()
    yy=net(x)
    toc()
    print(x.shape)
    print(yy.shape)
    prms = net.getnumberofparams(net,x)
    print(prms)
