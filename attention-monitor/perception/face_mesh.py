import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core import base_options as base_options_module


class FaceMeshDetector:
    def __init__(self):
        options = vision.FaceLandmarkerOptions(
            base_options=base_options_module.BaseOptions(
                model_asset_path="models/face_landmarker.task"
            ),
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

    def process(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.detector.detect(mp_image)

        landmarks = []

        if result.face_landmarks:
            h, w, _ = frame.shape
            for face in result.face_landmarks:
                pts = [(int(lm.x * w), int(lm.y * h)) for lm in face]
                landmarks = pts
                # draw dots
                for (x, y) in pts:
                    cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

        return frame, landmarks
