from tkinter.constants import NW

from PIL.ImageTk import PhotoImage
from PIL.Image import Image
import customtkinter

from modules.util.concept_maker.image.operations import crop_image

class EasyCropUIState:
    def __init__(self, image, image_size):
        self.bbox = (0, 0, 0, 0)
        self.image = image,
        self.image_size = image_size
        self.crop_start = (0, 0)
        self.crop_end = (0, 0)
        self.cropped_image = None
        self.fit_image = None


class EasyCropUI(customtkinter.CTkFrame):
    def __init__(self, master: any, image: Image, image_size: tuple[int, int], crophandler=None, **kwargs):
        super().__init__(master, **kwargs)

        self.state = EasyCropUIState(
            image,
            image_size
        )

        self.crophandler = crophandler

        # Image initialization
        self.state.fit_image = image
        image_to_crop = PhotoImage(self.state.fit_image)

        # Crop Canvas
        self.cropcanvas = customtkinter.CTkCanvas(
            self,
            width=512,
            height=512,
            scrollregion=(0, 0, self.state.fit_image.width, self.state.fit_image.height),
        )
        self.cropcanvas.create_image(
            0,
            0,
            image=image_to_crop,
            anchor="nw",
            tags="image",
        )
        self.cropcanvas.img = image_to_crop
        self.cropcanvas.bind("<Motion>", self.__mouse_move)
        self.cropcanvas.bind("<Button-1>", self.__crop_image)
        self.cropcanvas.bind("<Button-3>", self.__start_drag)
        self.cropcanvas.bind("<B3-Motion>", self.__update_drag)
        self.cropcanvas.xview_moveto(0)
        self.cropcanvas.yview_moveto(0)
        self.cropcanvas.grid(row=0, column=0, columnspan=2, sticky="nw")

        # Crop Canvas Scrolling
        self.vs_scrollbar = customtkinter.CTkScrollbar(self,
                                                       orientation="vertical",
                                                       command=self.cropcanvas.yview)
        self.vs_scrollbar.grid(row=0, column=2, sticky="ns")
        self.cropcanvas.configure(yscrollcommand=self.vs_scrollbar.set)

        self.hs_scrollbar = customtkinter.CTkScrollbar(self,
                                                       orientation="horizontal",
                                                       command=self.cropcanvas.xview)
        self.hs_scrollbar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.cropcanvas.configure(xscrollcommand=self.hs_scrollbar.set)

        # Crop Frame Selector
        self.cropframecombo = customtkinter.CTkComboBox(self, values=["512x512", "1024x1024"])
        self.cropframecombo.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="new")

        # Crop Button
        self.cropbutton = customtkinter.CTkButton(self, text="Crop", command=self.__crop_exit)
        self.cropbutton.grid(row=3, column=0, columnspan=4, padx=10, pady=10, sticky="new")

        # View Canvas
        self.viewcanvas = customtkinter.CTkCanvas(
            self, width=512, height=512)
        self.viewcanvas.img = self.state.cropped_image
        self.viewcanvas.grid(row=0, column=3, columnspan=1)

    def __crop_image(self, event):
        self.state.cropped_image = crop_image(
            self.state.fit_image,
            self.state.bbox
        )

        view_image = self.state.cropped_image
        if view_image.width > 512 or view_image.height > 512:
            view_image = view_image.resize((512, 512))
        view_image = PhotoImage(view_image)
        self.viewcanvas.create_image(0, 0, image=view_image, anchor=NW, tags="image")
        self.viewcanvas.img = view_image

    def __mouse_move(self, event):
        mouse_x = self.cropcanvas.canvasx(event.x)
        mouse_y = self.cropcanvas.canvasy(event.y)

        if self.cropframecombo.get() == "512x512":
            self.state.bbox = (
                min(max(mouse_x - 512 / 2, 0), self.state.fit_image.width - 512),
                min(max(mouse_y - 512 / 2, 0), self.state.fit_image.height - 512),
                min(max(mouse_x + 512 / 2, 512), self.state.fit_image.width),
                min(max(mouse_y + 512 / 2, 512), self.state.fit_image.height)
            )

        if self.cropframecombo.get() == "1024x1024":
            self.state.bbox = (
                min(max(mouse_x - 1024 / 2, 0), self.state.fit_image.width - 1024),
                min(max(mouse_y - 1024 / 2, 0), self.state.fit_image.height - 1024),
                min(max(mouse_x + 1024 / 2, 1024), self.state.fit_image.width),
                min(max(mouse_y + 1024 / 2, 1024), self.state.fit_image.height)
            )

        self.cropcanvas.delete("cropbox")
        self.cropcanvas.create_rectangle(
            self.state.bbox[0],
            self.state.bbox[1],
            self.state.bbox[2],
            self.state.bbox[3],
            width=4,
            outline="red",
            tags="cropbox",
        )

    def __start_drag(self, event):
        self.cropcanvas.scan_mark(event.x, event.y)

    def __update_drag(self, event):
        self.cropcanvas.scan_dragto(event.x, event.y, gain=1)

    def __crop_exit(self):
        if self.crophandler:
            self.crophandler(self.state.cropped_image)
        self.destroy()
