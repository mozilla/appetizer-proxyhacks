from proxyhack.wsgiapp import Application
import os

application = Application(os.environ['CONFIG_FILES'])
