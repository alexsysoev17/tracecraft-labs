import sys
from .cli import main, emit

try:
    sys.exit(main())
except (ValueError,PermissionError,TimeoutError) as error:
    emit({'status':'BLOCKED','error':str(error)})
    sys.exit(2)
