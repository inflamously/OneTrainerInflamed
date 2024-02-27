import argparse


class ConceptMakerArgs:
    imageFolder: str = ""

    def __init__(self):
        super(ConceptMakerArgs, self).__init__()

    def parse_args(self):
        parser = argparse.ArgumentParser("Concept Maker for OneTrainer")
        parser.add_argument(
            "--imageFolder",
            type=str,
            required=True,
            help="Directory of images to be converted to concepts"
        )
        try:
            self.__dict__ = parser.parse_args().__dict__
        except argparse.ArgumentTypeError:
            print("Error parsing arguments, invalid arguments passed")
        return self
