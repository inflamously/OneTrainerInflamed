from typing import List

import PIL.Image


def crop_diff(a: tuple[int, int], b: tuple[int, int]):
    return abs(a[0] - b[0]), abs(a[1] - b[1])


def crop_images(images: List[PIL.Image.Image], box: tuple[int, int, int, int]):
    return [crop_image(image, box) for image in images]


def crop_image(image: PIL.Image.Image, box: tuple[int, int, int, int]):
    # Swap left / right values if needed
    if box[0] > box[2]:
        box = (box[2], box[1], box[0], box[3])

    # Swap top / bottom values if needed
    if box[1] > box[3]:
        box = (box[0], box[3], box[2], box[1])

    return image.crop(box)


def resize_images(images: List[PIL.Image.Image], size):
    return [image.resize(size) for image in images]
