"""screen_capture_component demo."""

from component.observe.screen_capture_component import capture_screen_to_file


def run_demo():
    image_path = capture_screen_to_file(output_dir="component/observe/data")
    print(image_path)


if __name__ == "__main__":
    run_demo()
