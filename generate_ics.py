import os

from client import generate_calendar

uprn = os.getenv("UPRN")
assert uprn, "UPRN environment variable not set"

if __name__ == '__main__':
    calendar = generate_calendar(uprn)
    filename = os.getenv('OUTPUT_FILENAME', 'bin-calendar.ics')
    with open(filename, 'w+') as f:
        f.writelines(calendar.serialize_iter())
