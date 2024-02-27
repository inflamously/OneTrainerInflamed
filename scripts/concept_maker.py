import customtkinter

from modules.util.concept_maker.cm import ConceptMaker
from modules.util.concept_maker.cm_args import ConceptMakerArgs
from modules.util.concept_maker.ui.interactive_crop_ui import InteractiveCropUI


def main():
    cma = ConceptMakerArgs().parse_args()
    cm = ConceptMaker(cma)
    window = customtkinter.CTk()
    window.title("Interactive Crop")
    window.geometry("864x820")
    window.resizable(False, False)
    InteractiveCropUI(window, images=cm.images, filepath=cm.get_filepath())
    window.mainloop()


if __name__ == "__main__":
    main()
