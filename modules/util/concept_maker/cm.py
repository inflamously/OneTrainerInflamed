import os
from typing import List

from PIL import Image

from modules.util.concept_maker.cm_args import ConceptMakerArgs


class ConceptMaker:
    images: List[Image.Image] = []

    def __init__(self, args: ConceptMakerArgs):
        self.__parse_image_folder(args.imageFolder)

    def get_filepath(self):
        return self.path_to_images

    def __parse_image_folder(self, path_to_images: str):
        self.path_to_images = path_to_images

        try:
            image_types = (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
            for image in os.listdir(path_to_images):
                if image.endswith(image_types):
                    self.images.append(
                        Image.open(path_to_images + '/' + image)
                    )
        except FileNotFoundError:
            print("Could not open image folder, please check the path and try again.")
            self.images = []
