import os.path
import subprocess
from typing import List

from PIL.Image import Image
import customtkinter
from PIL.ImageTk import PhotoImage

from modules.util.concept_maker.ui.cm_cropui import EasyCropUI


class InteractiveCropUI(customtkinter.CTkFrame):
    def __init__(self, window, images: List[Image], filepath: str):
        super().__init__(window)

        self.window = window
        self.original_images = images
        self.filepath = filepath

        # Start crop process
        self.croptool = customtkinter.CTkButton(self, text="Start Crop", width=824, command=self.__start_crop)
        self.croptool.grid(row=0, column=0, padx=10, pady=10, sticky="nw")

        self.cropped_images = []

        # Crop Images frame
        self.imgframe = customtkinter.CTkCanvas(self,
                                                width=824,
                                                height=64,
                                                scrollregion=(0, 0, 10000, 64),
                                                confine=True)
        self.imgframe.xview_moveto(0)
        self.imgframe.yview_moveto(0)
        self.imgframe.grid(row=1, column=0, sticky="nwe")

        self.imglabels = [
            customtkinter.CTkLabel(self.imgframe,
                                   bg_color="gray",
                                   width=64,
                                   height=64,
                                   image=PhotoImage(img.resize((64, 64))),
                                   text="") for img in images
        ]

        # Crop image placeholders
        row = 1
        col = 0
        for i, imglabel in enumerate(self.imglabels):
            # if (i + 1) % 5 == 0:
            #     row += 1
            #     col = 0
            col += 1
            imglabel.grid(row=row, column=col, padx=10, pady=10, sticky="we")

        # Scrollbar
        self.hs_scrollbar = customtkinter.CTkScrollbar(self, orientation="horizontal", command=self.imgframe.xview)
        self.hs_scrollbar.grid(row=row + 1, column=0, columnspan=2, sticky="ew")
        self.imgframe.configure(xscrollcommand=self.hs_scrollbar.set)

        # Save images
        self.save_button = customtkinter.CTkButton(self, text="Save Images", width=824, command=self.__save_crop_images)
        self.save_button.grid(row=row + 2, column=0, columnspan=1, padx=10, pady=10, sticky="nw")

        # Generate Captions
        self.generate_captions_button = customtkinter.CTkButton(self, text="Generate Captions", width=824,
                                                                command=self.__generate_captions)
        self.generate_captions_button.grid(row=row + 3, column=0, columnspan=1, padx=10, pady=10, sticky="nw")

        # Frame
        self.grid(row=0, column=0, columnspan=4, padx=10, pady=10, sticky="nw")

    def __generate_captions(self):
        proc = subprocess.Popen("python generate_captions.py --model BLIP --sample-dir " + self.filepath,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        if proc:
            while proc.poll() is None:
                print(proc.stdout.readline().decode("utf-8"))

    def __save_crop_images(self):
        if self.filepath and os.path.exists(self.filepath):
            for i, img in enumerate(self.cropped_images):
                img.save(f"{self.filepath}/cropped_{i}.png")

    def __start_crop(self):
        self.cropped_images = []

        for img in self.original_images:
            normal_ratio = img.width > img.height
            aspect_ratio = \
                (img.width / img.height) \
                    if normal_ratio else (img.height / img.width)

            # Given image X W and H, we want to display it in a 512x512 window preserving aspect ratio
            image_size = (512, 512 / aspect_ratio) if normal_ratio else (512 / aspect_ratio, 512)

            cropui = EasyCropUI(
                self.window,
                img,
                image_size,
                crophandler=self.__crop_images
            )
            cropui.grid(row=1, column=0, columnspan=4, padx=10, pady=10, sticky="nw")

    def __update_images(self):
        if 0 < len(self.imglabels) == len(self.cropped_images) > 0:
            for i, img in enumerate(self.cropped_images):
                if img:
                    resized_photo_image = PhotoImage(img.resize((64, 64)))
                    self.imglabels[i].configure(image=resized_photo_image)

    def __crop_images(self, image):
        self.cropped_images.append(image)
        self.__update_images()
