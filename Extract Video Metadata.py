#!/usr/bin/env python3

import json
import sys
import sh
from sh import ffprobe
from os.path import basename
from glob import glob

def get(filename):
    j = ffprobe("-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", filename)
    t = json.loads(str(j))
    return t

def streams(metadata):
    # return audio and video stream
    streams = metadata['streams']
    audio = None
    video = None
    for stream in streams:
        if audio and video and (stream['codec_type'] in ['audio', 'video']):
            #print(metadata)
            raise ValueError("not exactly one audio and one video stream")
        if stream['codec_type'] == 'audio':
            audio = stream
        elif stream['codec_type'] == 'video':
            video = stream          
    return audio, video


def check(filename, details=False):
    try:
        metadata = get(filename)
    except:
        return(name, "Error - could not check file - maybe not a video?", "", "", "", "", "", "", "", "")
    name = basename(filename)
    try:
        audio, video = streams(metadata)
    except ValueError:
        return(name, "Error - more than two AV streams in file", "", "", "", "", "", "", "", "")
    if details:
        print(data)  
    container = metadata['format']
    duration = str(int(float(container['duration'])))
    try:
        cformat = container['tags']['major_brand']
    except KeyError:
        cformat = "unknown"
    if video:
        width, height = video['width'], video['height']
        vcodec_name, r_frame_rate = video['codec_name'], video['r_frame_rate']
    else:
        width, height = "", ""
        vcodec_name, r_frame_rate = "", ""
    #field_order = video['field_order']
    if audio:
        acodec_name, sample_rate, channels = audio['codec_name'], audio['sample_rate'], audio['channels']
    else:
        acodec_name, sample_rate, channels = "", "", ""
    return (name, duration, cformat, vcodec_name, width, height, r_frame_rate, acodec_name, sample_rate, channels)


FILES = sys.argv[1:]
#glob(PATH+"/*")

print("name,duration,container format,video codec,width,height,frame rate,audio codec,sample rate,channels")
for f in FILES:
    print(",".join(map(str,check(f))))

