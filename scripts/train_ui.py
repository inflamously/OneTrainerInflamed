from util.import_util import script_imports

script_imports()

from modules.ui.TrainUI import TrainUI


def main():
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    ui = TrainUI()
    ui.mainloop()


if __name__ == '__main__':
    main()
