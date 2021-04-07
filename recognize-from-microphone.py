import sys
import libs.fingerprint as fingerprint
import argparse
from itertools import zip_longest
from termcolor import colored
from libs.config import get_config
from libs.reader_microphone import MicrophoneReader
from libs.visualiser_console import VisualiserConsole as visual_peak
from libs.visualiser_plot import VisualiserPlot as visual_plot
from libs.db_sqlite import SqliteDatabase


if __name__ == '__main__':
    config = get_config()
    db = SqliteDatabase()
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-s', '--seconds', nargs='?')
    args = parser.parse_args()

    if not args.seconds:
        parser.print_help()
        sys.exit(0)

    seconds = int(args.seconds)
    chunksize = 2**12 #4096
    channels = 2 # 1=mono, 2=stereo
    record_forever = False
    visualise_console = bool(config['mic.visualise_console'])
    visualise_plot = bool(config['mic.visualise_plot'])
    reader = MicrophoneReader(None)
    reader.start_recording(seconds=seconds, chunksize=chunksize, channels=channels)
    msg = ' * started recording..'
    print(colored(msg, attrs=['dark']))

    while True:
        bufferSize = int(reader.rate / reader.chunksize * seconds)

        for i in range(0, bufferSize):
            nums = reader.process_recording()

            if visualise_console:
                msg = colored('   %05d', attrs=['dark']) + colored(' %s', 'green')
                print(msg % visual_peak.calc(nums))
            else:
                msg = '     processing %d of %d..' % (i, bufferSize)
                print(colored(msg, attrs=['dark']))

        if not record_forever: break

    if visualise_plot:
        data = reader.get_recorded_data()[0]
        visual_plot.show(data)

    reader.stop_recording()
    msg = ' * recording has been stopped'
    print(colored(msg, attrs=['dark']))


    def grouper(iterable, n, fillvalue=None):
        args = [iter(iterable)] * n
        return (filter(None, values) for values in zip_longest(fillvalue=fillvalue, *args))

    data = reader.get_recorded_data()
    msg = ' * recorded %d samples'
    print(colored(msg, attrs=['dark']) % len(data[0]))
    Fs = fingerprint.DEFAULT_FS
    channel_amount  = len(data)
    result = set()
    matches = []

    def find_matches(samples, Fs=fingerprint.DEFAULT_FS):
        hashes = fingerprint.fingerprint(samples, Fs=Fs)
        return return_matches(hashes)

    def return_matches(hashes):
        mapper = {}
        for hash, offset in hashes:
            mapper[hash.upper()] = offset

        values = mapper.keys()

        for split_values in grouper(values, 1000):
            query = """
                SELECT upper(hash), song_fk, offset
                FROM fingerprints
                WHERE upper(hash) IN (%s)
            """
            split_values = list(split_values)
            query = query % ', '.join('?' * len(split_values))
            x = db.executeAll(query, split_values)
            matches_found = len(x)

            if matches_found > 0:
                msg = '    ** found %d hash matches (step %d/%d)'
                print(colored(msg, 'green') % (matches_found, len(split_values), len(values)))
            else:
                msg = '    ** no matches found (step %d/%d)'
                print(colored(msg, 'red') % (len(split_values), len(values)))

            for hash, sid, offset in x:
                yield sid, offset

    for channeln, channel in enumerate(data):
        msg = '    fingerprinting channel %d/%d'
        print(colored(msg, attrs=['dark']) % (channeln+1, channel_amount))
        matches.extend(find_matches(channel))
        msg = '    finished channel %d/%d, got %d hashes'
        print(colored(msg, attrs=['dark']) % (channeln+1, channel_amount, len(matches)))

    def align_matches(matches):
        diff_counter = {}
        largest = 0
        largest_count = 0
        song_id = -1

        for tup in matches:
            sid, diff = tup

            if diff not in diff_counter:
                diff_counter[diff] = {}

            if sid not in diff_counter[diff]:
                diff_counter[diff][sid] = 0

            diff_counter[diff][sid] += 1

            if diff_counter[diff][sid] > largest_count:
                largest = diff
                largest_count = diff_counter[diff][sid]
                song_id = sid

        songM = db.get_song_by_id(song_id)
        return {"SONG_ID" : song_id, "SONG_NAME" : songM[1], "ARTIST" : songM[2], "GENRE" : songM[4], "BPM" : songM[5]}

    total_matches_found = len(matches)
    print('')

    if total_matches_found > 0:
        msg = ' ** totally found %d hash matches'
        print(colored(msg, 'green') % total_matches_found)
        song = align_matches(matches)
        msg = ' => song: %s\n'
        msg += '    artist: %s \n'
        msg += '    genre: %s \n'
        msg += '    bpm: %d \n'
        print(colored(msg, 'green') % (song['SONG_NAME'], song['ARTIST'], song['GENRE'], song['BPM']))
    else:
        msg = ' ** no matches found at all'
        print(colored(msg, 'red'))