import customtkinter
from PIL.Image import Image
from PIL.ImageTk import PhotoImage

from modules.util.concept_maker.image.operations import crop_diff, crop_image


class ImageCropState:
    def __init__(self, image: Image, image_size: tuple[int, int]):
        self.fit_image = image.resize(size=(int(image_size[0]), int(image_size[1])))
        self.cropped_image = None
        self.crop_origin = (0, 0)
        self.crop_end = (0, 0)
        self.rectangle_mode = False


class ImageCropUI(customtkinter.CTkFrame, ImageCropState):
    def __init__(self, master, image: Image, image_size: tuple[int, int]):
        super().__init__(master)

        self.state = ImageCropState(image, image_size)

        # Image initialization
        self.state.fit_image = image.resize(size=(int(image_size[0]), int(image_size[1])))
        image_to_crop = PhotoImage(self.state.fit_image)

        # Crop Canvas
        self.cropcanvas = customtkinter.CTkCanvas(
            self,
            width=self.state.fit_image.width,
            height=self.state.fit_image.height)
        self.cropcanvas.create_image(0, 0, image=image_to_crop, anchor="nw", tags="image")
        self.cropcanvas.img = image_to_crop
        self.cropcanvas.grid(row=0, column=0)

        # Crop UI
        self.cropcanvas.bind("<B1-Motion>", self.__update_crop)
        self.cropcanvas.bind("<Button-1>", self.__start_crop)
        self.cropcanvas.bind("<ButtonRelease-1>", self.__end_crop)

        # View Canvas
        self.viewcanvas = customtkinter.CTkCanvas(
            self, width=image_size[0], height=image_size[1])
        self.viewcanvas.img = self.state.cropped_image
        self.viewcanvas.grid(row=0, column=1, columnspan=2)

        # Self crop actions
        self.rectmodeenable = customtkinter.CTkButton(self,
                                                      text="Enable Rectangle Mode",
                                                      command=self.__enable_rectangle_mode)
        self.rectmodeenable.grid(row=1, column=1, padx=10, pady=10, sticky="new")
        self.rectmodedisable = customtkinter.CTkButton(self,
                                                       text="Disable Rectangle Mode",
                                                       command=self.__disable_rectangle_mode)
        self.rectmodedisable.grid(row=1, column=2, padx=10, pady=10, sticky="new")

        self.rectmodelabel = customtkinter.CTkLabel(self, )
        self.__update_rectmodelabel_text()
        # self.rectmodelabel.grid(row=1, column=1, pady=10, padx=10, sticky="new")

        self.cropbutton = customtkinter.CTkButton(self, text="Crop", command=self.__crop_image)
        self.cropbutton.grid(row=1, column=0, pady=10, padx=10, sticky="new")
        self.cropbutton.configure(state="disabled")

        # Frame
        self.grid(row=0, column=0, padx=10, pady=10, sticky="nw")

    def __crop_box(self):
        return crop_diff(self.state.crop_end, self.state.crop_origin)

    def __crop_image(self):
        self.state.cropped_image = crop_image(
            self.state.fit_image,
            (
                self.state.crop_origin[0],
                self.state.crop_origin[1],
                self.state.crop_end[0],
                self.state.crop_end[1]
            )
        )
        self.cropped_image_photo = PhotoImage(self.state.cropped_image)
        self.viewcanvas.create_image(0, 0, image=self.cropped_image_photo, anchor="nw", tags="image")
        self.viewcanvas.img = self.cropped_image_photo

    def __update_crop_button(self):
        self.cropbutton.configure(
            state="normal" if self.state.crop_end[0] > 0 and self.state.crop_end[1] > 0 else "disabled"
        )

    def __start_crop(self, event):
        self.state.crop_origin = (event.x, event.y)
        self.state.crop_end = (0, 0)
        self.cropcanvas.delete("cropbox")
        self.__update_crop_button()
        print("Start Crop:", self.state.crop_origin)

    def __calc_crop_end(self, event):
        # TODO: Refactor event.x and event.y to be a tuple
        return min(event.x, self.state.fit_image.width), min(event.y, self.state.fit_image.height)

    def __update_crop(self, event):
        self.state.crop_end = self.__calc_crop_end(event)

        crop_end = [self.state.crop_end[0], self.state.crop_end[1]]
        if self.state.rectangle_mode:
            crop_end[0] = max(self.state.crop_end[0], self.state.crop_end[1])

        print("State", crop_end)

        self.cropcanvas.delete("cropbox")
        self.cropcanvas.create_rectangle(
            max(self.state.crop_origin[0], 0),
            max(self.state.crop_origin[1], 0),
            crop_end[0],
            crop_end[1] if not self.state.rectangle_mode else crop_end[0],
            tags="cropbox",
            width=4,
            outline="red",
        )
        self.__update_crop_button()
        # print("Update Crop:", self.state.crop_end)

    def __end_crop(self, event):
        print("End Crop:", self.state.crop_end)
        print("Crop Size:", self.__crop_box())
        # self.cropcanvas.delete("cropbox")

    def __enable_rectangle_mode(self):
        self.state.rectangle_mode = True
        self.__update_rectmodelabel_text()
        print("Rectangle Mode:", self.state.rectangle_mode)

    def __disable_rectangle_mode(self):
        self.state.rectangle_mode = False
        self.__update_rectmodelabel_text()
        print("Rectangle Mode:", self.state.rectangle_mode)

    def __update_rectmodelabel_text(self):
        self.rectmodelabel.configure(
            text="Rectangle Mode:{}".format("enabled" if self.state.rectangle_mode else "disabled"))

