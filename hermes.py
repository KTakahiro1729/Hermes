import bpy

import ast, copy, logging, traceback, json, socket
from ctypes import c_char_p
from contextlib import _RedirectStream, redirect_stdout, redirect_stderr
from io import StringIO


def sendall_sock(sock, target_sock, msg, csize = 1024):
    if not msg.endswith(b"\0"):
        msg += b"\0"
    while msg:
        send, left = msg[:csize],msg[csize:]
        sock.sendto(send,target_sock)
        msg = left

def recvall(target):
    target.settimeout(0.01)
    received = b""
    while True:
        data, client = target.recvfrom(4096)
        target.settimeout(None)
        received += data
        if received.endswith(b"\0"):
            break
    return received[:-1], client

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

def port_can_use(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    result = False
    try:
        sock.bind(("localhost", port))
        result = True
    except OSError:
        result = False
    finally:
        sock.close()
        return result


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


def exec_eval(code_ast, fname = "<ast>"):
    """refined exec func with a returning value if the last is expression"""

    init_ast = copy.deepcopy(code_ast)
    init_ast.body = code_ast.body[:-1]

    last_ast = copy.deepcopy(code_ast)
    last_ast.body = code_ast.body[-1:]

    exec(compile(init_ast, "<ast>", "exec"), globals())
    if type(last_ast.body[0]) == ast.Expr:
        return eval(compile(_convertExpr2Expression(last_ast.body[0]), "<ast>", "eval"),globals())
    else:
        exec(compile(last_ast, fname, "exec"),globals())

def exec_code(code):
    return mount_stdioe(exec_eval, [], code)

def dict2ast(dict_):

    if type(dict_) == list:
        return [dict2ast(d) for d in dict_]
    if "term" in dict_.keys():
        return dict_["term"]
    ntype = getattr(ast,dict_.pop("ntype"))
    d_fields = dict_.pop("fields")
    n_fields = {fname: dict2ast(d) for fname, d in d_fields.items()}
    node = ntype(**{**n_fields,**dict_})
    return node

class CONSOLE_MT_code_receptor(bpy.types.Operator):
    """Recieve python snippets from extern and execute them"""
    bl_idname = "script.receive_python_snippets"
    bl_label = "start recieving python snippets"
    bl_description = "Recieve python snippets from Jupyter notebook and execute"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    # _process = None
    _sock = None
    _logger     = logging.getLogger("modal")

    code = ""
    response = ""
    code_port = -1
    def code_recv(self):
        """recieve code and send back the results"""

        # start receiveing
        try:
            data, client = recvall(self._sock)
        except socket.timeout:
            return
        self.code = json.loads(data.decode("utf-8"))["code"]
        # self.report({"INFO"}, "got {0}".format(data))
        evl, out, exc = exec_code(dict2ast(self.code))
        try:
            self.response = json.dumps({
                "evl": evl,
                "out": out,
                "exc": exc
            })
        except TypeError:
            self.response = json.dumps({
                "evl": str(evl),
                "out": out,
                "exc": exc
            })
        print(out)
        sendall_sock(self._sock, client, self.response.encode("utf-8"))

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self._sock.close()
            self.report({"INFO"}, "end hermers")
            self.cancel(context)
            return {'FINISHED'}

        if event.type == 'TIMER':
            self.code_recv()

        return {'PASS_THROUGH'}

    def execute(self, context):
        # make timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)

        # find open port
        for i in range(10):
            self.code_port = i + 8890
            if port_can_use(self.code_port):
                self.report({"INFO"}, "hermes code port at {0}".format(self.code_port))
                break
            else:
                self.report({"INFO"}, "port {0} was used".format(self.code_port))
        else:
            self.report({"ERROR"}, "failed to find open port")
            return {'CANCELLED'}

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("localhost", self.code_port))
        logging.debug("start hermes")
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
