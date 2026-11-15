def enqueue_transcode(video_id):
    from app.worker import transcode_video

    transcode_video.delay(video_id)
