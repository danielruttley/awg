import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

import os
import sys
import time
from random import shuffle

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from math import log10,floor,ceil
import PIL.Image as PILImage

if __name__ == '__main__':
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from networking.server import PyServer

from camera.windows_setup import configure_path
configure_path()

from camera.source import TLCameraSDK

class ArrayNormaliser():
    def __init__(self,name,port,start_freq_MHz,start_amp=None,iterations=3,channel=0,
                 exposure_ms=0.5,roi=None,distance_between_traps=10,
                 scale_index=1,trap_waist_guess=30):
        """Define the ArrayNormaliser class.
        
        Parameters
        ----------
        port : int
            The port to send messages to the AWG server on.
        """
        self.name = name
        self.channel = int(channel)
        self.distance_between_traps = distance_between_traps
        self.trap_df = pd.DataFrame()
        
        self.exposure_ms = exposure_ms
        self.roi = roi
        self.trap_waist_guess = trap_waist_guess
        
        self.scale_index = scale_index
        
        self.start_freq_MHz = start_freq_MHz
        
        if start_amp == None:
            start_amp = [1/len(start_freq_MHz)]*len(start_freq_MHz)
        self.start_amp = start_amp
            
        self.server = PyServer(host='', port=int(port))
        self.server.start()
        
        # filename = self.name+'_normaliser_param.txt'
        # filename = os.path.abspath(__file__)        
        # self.server.add_message(1,'load='+filename+'#'*1000)
        
        self.set_freq(self.start_freq_MHz,self.start_amp)
        # self.fit_single_traps()
        # loaded_df = pd.read_csv('trap_df.csv',index_col=0)
        # for key in loaded_df.keys():
        #     if ('single' in key) or ('freq_MHz' in key):
        #         self.trap_df[key] = loaded_df[key]
        
        # self.trap_df['start_amp_0'] = self.start_amp
        # print(self.trap_df)
        
        # for i in range(iterations):
        #     self.fit_traps(i)
        
    def set_freq(self,start_freq_MHz,start_amp=None):
        segment = 0
        if start_amp is None:       
            message = 'set_complete_data=[[{},{},{},{}]]'.format(self.channel,
                                                                 segment,
                                                                 "'start_freq_MHz'",
                                                                 start_freq_MHz)
        else:
            message = ('set_complete_data=[[{},{},{},{}],[{},{},{},{}]]'
                      ''.format(self.channel,segment,"'start_freq_MHz'",start_freq_MHz,
                                self.channel,segment,"'start_amp'",start_amp))
        logging.info('Sending {}.'.format(message))
        self.server.add_message(1,message+'#'*1000)
        
    def take_image(self):
        roi = self.roi
        with TLCameraSDK() as sdk:
            available_cameras = sdk.discover_available_cameras()
            if len(available_cameras) < 1:
                print("no cameras detected")

            with sdk.open_camera(available_cameras[0]) as camera:
                print('connected to camera {}'.format(camera.name))

                camera.exposure_time_us = int(self.exposure_ms*1e3) # set exposure to 0.5 ms
                camera.frames_per_trigger_zero_for_unlimited = 0  # start camera in continuous mode
                camera.image_poll_timeout_ms = 10000  # 10 second polling timeout
                old_roi = camera.roi  # store the current roi
                
                print(roi)
                if roi != None:
                    camera.roi = roi  # set roi to be at origin point (100, 100) with a width & height of 500

                """
                uncomment the lines below to set the gain of the camera and read it back in decibels
                """
                #if camera.gain_range.max > 0:
                #    db_gain = 6.0
                #    gain_index = camera.convert_decibels_to_gain(db_gain)
                #    camera.gain = gain_index
                #    print(f"Set camera gain to {camera.convert_gain_to_decibels(camera.gain)}")

                camera.arm(2)

                camera.issue_software_trigger()

                frame = camera.get_pending_frame_or_null()
                if frame is not None:
                    print("frame #{} received!".format(frame.frame_count))
                    frame.image_buffer  # .../ perform operations using the data from image_buffer

                    #  NOTE: frame.image_buffer is a temporary memory buffer that may be overwritten during the next call
                    #        to get_pending_frame_or_null. The following line makes a deep copy of the image data:
                    image_buffer_copy = np.copy(frame.image_buffer)
                else:
                    print("timeout reached during polling, program exiting...")
                    image_buffer_copy = None
                    
                camera.disarm()
                camera.roi = old_roi  # reset the roi back to the original roi
                return image_buffer_copy
            
    def fit_single_traps(self):
        logging.info('Getting single trap coordinates.')
        for i,freq in enumerate(self.start_freq_MHz):
            self.set_freq([freq],[1/len(self.start_freq_MHz)])
            time.sleep(1)
            
            array = self.take_image()
            print(np.max(array))
            
            # plt.imshow(array)
            # plt.show()
            
            # x,y = np.meshgrid(np.arange(array.shape[1]),np.arange(array.shape[0]))
            
            cent_ind = [x for x in np.unravel_index(array.argmax(), array.shape)]            
            print(cent_ind[1],cent_ind[0])
            
            x0 = cent_ind[1]
            y0 = cent_ind[0]
            wx = self.trap_waist_guess
            
            xmin = max(round(x0-1.5*wx),0)
            xmax = min(round(x0+1.5*wx),array.shape[1])
            ymin = max(round(y0-1.5*wx),0)
            ymax = min(round(y0+1.5*wx),array.shape[0])
            print(xmin,ymin,xmax,ymax)
            roi = array[ymin:ymax,xmin:xmax]
            print('array_max',np.max(array))
            print('roi_max',np.max(roi))
            
            max_val = np.max(roi)
            x,y = np.meshgrid(np.arange(xmin,xmax),np.arange(ymin,ymax))
            
            popt, pcov = curve_fit(self.gaussian2D, (x,y), roi.ravel(), p0=[np.max(roi),cent_ind[1],cent_ind[0],self.trap_waist_guess,self.trap_waist_guess,0])
            perr = np.sqrt(np.diag(pcov))
            self.trap_df.loc[i,'freq_MHz'] = freq
            for arg,val,err in zip(self.gaussian2D.__code__.co_varnames[2:],popt,perr):
                prec = floor(log10(err))
                err = round(err/10**prec)*10**prec
                val = round(val/10**prec)*10**prec
                if prec > 0:
                    valerr = '{:.0f}({:.0f})'.format(val,err)
                else:
                    valerr = '{:.{prec}f}({:.0f})'.format(val,err*10**-prec,prec=-prec)
                print(arg,'=',valerr)
                self.trap_df.loc[i,'single_'+arg] = val
                self.trap_df.loc[i,'single_'+arg+'_err'] = err
            print('\n')
            self.trap_waist_guess = popt[3]
            
        print(self.trap_df)
    
    def fit_traps(self,iteration=0,plot=False):
        logging.info('Fitting multitrap image.')
        self.set_freq(self.start_freq_MHz,self.start_amp)
        time.sleep(5)
        
        array = self.take_image()
        print(np.max(array))
        
        popts = []
        perrs = []
        for i, row in self.trap_df.iterrows():
            print(i)
            x0 = row['single_x0']
            y0 = row['single_y0']
            wx = row['single_wx']
            wy = row['single_wy']
            theta = row['single_theta']
            print(x0,y0)
            xmin = max(round(x0-1.5*wx),0)
            xmax = min(round(x0+1.5*wx),array.shape[1])
            ymin = max(round(y0-1.5*wx),0)
            ymax = min(round(y0+1.5*wx),array.shape[0])
            print(xmin,ymin,xmax,ymax)
            roi = array[ymin:ymax,xmin:xmax]
            print('array_max',np.max(array))
            print('roi_max',np.max(roi))
            max_val = np.max(array)
            x,y = np.meshgrid(np.arange(xmin,xmax),np.arange(ymin,ymax))
            # plt.pcolormesh(x,y,roi)
            # plt.colorbar()
            # plt.show()
            popt, pcov = curve_fit(self.gaussian2D, (x,y), roi.ravel(), p0=[max_val,x0,y0,wx,wy,theta])
            perr = np.sqrt(np.diag(pcov))
            popts.append(popt)
            perrs.append(perr)
            for arg,val,err in zip(self.gaussian2D.__code__.co_varnames[2:],popt,perr):
                prec = floor(log10(err))
                err = round(err/10**prec)*10**prec
                val = round(val/10**prec)*10**prec
                if prec > 0:
                    valerr = '{:.0f}({:.0f})'.format(val,err)
                else:
                    valerr = '{:.{prec}f}({:.0f})'.format(val,err*10**-prec,prec=-prec)
                print(arg,'=',valerr)
                self.trap_df.loc[i,'multi_{}_{}'.format(iteration,arg)] = val
                self.trap_df.loc[i,'multi_{}_{}_err'.format(iteration,arg)] = err
            print('\n')
        
            self.trap_df.loc[i,'multi_{}_sum'.format(iteration)] = roi.sum().astype('float64')
        
        if plot:
            fitted_img = np.zeros_like(array).astype('float64')
            x, y = np.meshgrid(np.arange(array.shape[1]), range(array.shape[0]))
            for popt in popts:
                # print(self.gaussian2D((x,y),*popt).reshape(array.shape[0],array.shape[1]))
                fitted_img += self.gaussian2D((x,y),*popt).reshape(array.shape[0],array.shape[1]).astype('float64')

            fig, (ax1,ax2) = plt.subplots(1, 2)
            fig.set_size_inches(9, 5)
            fig.set_dpi(100)
            c1 = ax1.pcolormesh(x,y,array,cmap=plt.cm.viridis,shading='auto')
            ax1.invert_yaxis()
            ax1.set_title('camera image')
            fig.colorbar(c1,ax=ax1,label='pixel count')
            c2 = ax2.pcolormesh(x,y,fitted_img,cmap=plt.cm.viridis,shading='auto')
            ax2.invert_yaxis()
            ax2.set_title('fitted array')
            fig.colorbar(c2,ax=ax2,label='intensity (arb.)')
            fig.tight_layout()
            plt.show()
        
        # self.trap_df['start_amp_{}'.format(iteration+1)] = self.trap_df['multi_{}_I0'.format(iteration)].mean()/self.trap_df['multi_{}_I0'.format(iteration)]
        # self.trap_df['start_amp_{}'.format(iteration+1)] = self.trap_df['start_amp_{}'.format(iteration+1)]*0.125/self.trap_df['start_amp_{}'.format(iteration+1)].mean()
        
        self.trap_df['start_amp_{}'.format(iteration+1)] = self.trap_df['start_amp_{}'.format(iteration)]*(self.trap_df['multi_0_I0'].mean()/self.trap_df['multi_{}_I0'.format(iteration)])**self.scale_index
        
        # self.trap_df['start_amp_{}'.format(iteration+1)] = self.trap_df['start_amp_{}'.format(iteration)]*(self.trap_df['multi_0_sum'].mean()/self.trap_df['multi_{}_sum'.format(iteration)])
        
        self.trap_df.to_csv('trap_df.csv')
        
        self.start_amp = list(self.trap_df['start_amp_{}'.format(iteration+1)])
        
        self.set_freq(self.start_freq_MHz,self.start_amp)
            
    def gaussian2D(self,xy_tuple,I0,x0,y0,wx,wy,theta):
        (x,y) = xy_tuple
        sigma_x = wx/2
        sigma_y = wy/2 #function defined in terms of sigmax, sigmay
        a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
        b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
        c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
        g = I0*np.exp( - (a*((x-x0)**2) + 2*b*(x-x0)*(y-y0) 
                                + c*((y-y0)**2)))
        return g.ravel()
        
if __name__ == '__main__':
    name = 'AWG2'
    port = 8740
    start_freq_MHz = [106,104,102,100,98,96,94,92]
    start_amp = [0.125]*len(start_freq_MHz)
    start_amp = None
    iterations = 10
    channel = 0
    exposure_ms = 20
    roi = (197,189,416,900)
    scale_index = 1
    distance_between_traps = 10
    
    save_directory = r"Z:\Tweezer\Experimental Results\2022\August\12\AWG2 array images\varying global array amplitude 8 traps\\"   
    
    norm = ArrayNormaliser(name=name,
                           port=port,
                           start_freq_MHz=start_freq_MHz,
                           start_amp=start_amp,
                           iterations=iterations,
                           channel=channel,
                           exposure_ms=exposure_ms,
                           roi = roi,
                           scale_index = scale_index,
                           distance_between_traps=distance_between_traps)
    
    start_amps = list(np.linspace(0.01,0.4,16))
    shuffle(start_amps)
    
    print(start_amps)
    
    for i,start_amp in enumerate(start_amps):
        filepath = save_directory+str(start_amp)+'.png'
        time.sleep(1)
        print('\n--- IMAGE {} of {} ---'.format(i+1,len(start_amps)))
        print('set amp to ',start_amp)
        norm.start_amp = [start_amp]*len(norm.start_freq_MHz)
        norm.set_freq(norm.start_freq_MHz,norm.start_amp)
        
        time.sleep(5)
        print('save image as',filepath)
        array = norm.take_image()
        array = (array*int(2**16/2**10)).astype('uint16')
        PILImage.fromarray(array).save(filepath)

    # norm.set_freq([104,108])
    
    # roi = (1177, 227, 1239, 289)
    # image = norm.take_image(roi=roi)
    # plt.imshow(image)
    time.sleep(5)
    # print(norm.trap_df)
    # norm.trap_df.to_csv('trap_df.csv')
