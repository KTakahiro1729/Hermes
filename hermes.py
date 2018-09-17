import bpy

import ast, copy, logging, traceback, json, socket
from multiprocessing import Process, Value, Array, Manager
from ctypes import c_char_p
from contextlib import _RedirectStream, redirect_stdout, redirect_stderr
from io import StringIO

bl_info = {
    "name" : "Hermes -Jupyter for Blender-",
    "author" : "Allosteric",
    "version" : (0,1),
    "blender" : (2, 79, 0),
    "location" : "Python Console",
    "description" : "Receive python snippets from jupyter notebook and execute",
    "warning" : "",
    "support" : "TESTING",
    "wiki_url" : "",
    "tracker_url" : "",
    "category" : "Development",
}

def code_recv(code, has_changed, receptor_alive, response):
    """recieve code and send back the results"""
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("code receptor")
    logger.debug("start")

    # make socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("localhost", 8887))

    # start recieveing
    while receptor_alive.value:
        data, client = sock.recvfrom(4096)
        code.value = data.decode("utf-8")
        has_changed.value = 1
        logger.debug("got {0}".format(data))
        while has_changed.value:
            pass
        sock.sendto(response.value.encode("utf-8"), client)

    # terminate process
    sock.close()
class redirect_stdin(_RedirectStream):
    _stream = "stdin"
def mount_stdioe(func, stdins, *args, **kwargs):
    """mount standard in, out, exception"""
    stdin = StringIO()
    stdin.writelines(stdins)
    stdin.seek(0)

    func_return = None
    stdout = StringIO()
    stdexc = None
    try:
        with redirect_stdin(stdin), redirect_stdout(stdout):
            func_return = func(*args, **kwargs)
    except Exception:
        stdexc = traceback.format_exc()
    stdout = stdout.getvalue()
    return func_return, stdout, stdexc

def _convertExpr2Expression(Expr):
    """get ast.Expr and return ast.Expression"""
    Expr.lineno = 0
    Expr.col_offset = 0
    result = ast.Expression(Expr.value, lineno=0, col_offset = 0)
    return result

def exec_eval(code):
    """refined exec func with a returning value if the last is expression"""
    code_ast = ast.parse(code)

    init_ast = copy.deepcopy(code_ast)
    init_ast.body = code_ast.body[:-1]

    last_ast = copy.deepcopy(code_ast)
    last_ast.body = code_ast.body[-1:]

    exec(compile(init_ast, "<ast>", "exec"), globals())
    if type(last_ast.body[0]) == ast.Expr:
        return eval(compile(_convertExpr2Expression(last_ast.body[0]), "<ast>", "eval"),globals())
    else:
        exec(compile(last_ast, "<ast>", "exec"),globals())

def exec_code(code):
    return mount_stdioe(exec_eval, [], code)

class CONSOLE_MT_code_receptor(bpy.types.Operator):
    """Recieve python snippets from extern and execute them"""
    bl_idname = "script.recieve_python_snippets"
    bl_label = "start recieving python snippets"
    bl_description = "Recieve python snippets from Jupyter notebook and execute"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _process = None

    _logger     = logging.getLogger("modal")
    _out_logger = logging.getLogger("stdout")
    _exc_logger = logging.getLogger("excption")
    _evl_logger = logging.getLogger("last_expr")

    manager = Manager()
    code = manager.Value(c_char_p,"")
    response = manager.Value(c_char_p,"")
    has_changed = Value("i",0)
    receptor_alive = Value("i",1)


    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.receptor_alive.value = 0
            self._process.terminate()
            self._logger.debug("end")
            self.cancel(context)
            return {'FINISHED'}

        if event.type == 'TIMER':
            if self.has_changed.value:
                evl, out, exc = exec_code(self.code.value)
                try:
                    self.response.value = json.dumps({
                        "evl": evl,
                        "out": out,
                        "exc": exc
                    })
                except TypeError:
                    self.response.value = json.dumps({
                        "evl": str(evl),
                        "out": out,
                        "exc": exc
                    })
                self.has_changed.value = 0
                self._exc_logger.debug(exc)
                self._out_logger.debug(out)
                self._evl_logger.debug(evl)


        return {'PASS_THROUGH'}

    def execute(self, context):
        # make timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)

        # run socket in subprocess
        self._process = Process(target = code_recv,
            args=(self.code, self.has_changed, self.receptor_alive, self.response))
        self._process.daemon = True
        self._process.start()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

def menu_fn(self, context):
    self.layout.separator()
    self.layout.operator(CONSOLE_MT_code_receptor.bl_idname)

def register():
    bpy.utils.register_module(__name__)
    bpy.types.CONSOLE_MT_console.append(menu_fn)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.CONSOLE_MT_console.remove(menu_fn)
if __name__ == "__main__":
    register()
