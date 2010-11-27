import subprocess
import os

def main():
    path = os.path.join(os.environ['CONFIG_FILES'], 'sites')
    if not os.path.exists(path):
        print 'Making %s' % path
        os.makedirs(path)
    if not os.path.exists(os.path.join(path, '.git')):
        print 'Calling git init on %s' % path
        subprocess.call(['git', 'init'], cwd=path)

if __name__ == '__main__':
    main()
