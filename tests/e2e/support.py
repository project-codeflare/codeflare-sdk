import random
import string

def read_file(file_name):
    try:
        with open(file_name, 'rb') as file:
            return file.read()
    except IOError as e:
        raise e


alphabet = string.ascii_lowercase + string.digits
def random_choice():
    return ''.join(random.choices(alphabet, k=5))
