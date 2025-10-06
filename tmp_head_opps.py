import os
import glob

OUT_DIR = os.path.join(os.path.dirname(__file__), 'out')

def main():
    files = glob.glob(os.path.join(OUT_DIR, 'opportunities_*.txt'))
    if not files:
        print('no files')
        return
    latest = sorted(files)[-1]
    print('latest:', latest)
    with open(latest, 'r', encoding='utf-8') as fh:
        for i, line in enumerate(fh):
            if i >= 200:
                break
            print(f'{i+1:03d}: {line.rstrip()}')

if __name__ == '__main__':
    main()
