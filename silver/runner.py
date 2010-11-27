from proxyhack.wsgiapp import Application
import os

application = Application(os.path.join(os.environ['CONFIG_FILES'], 'sites'))
