from IPython.core.interactiveshell import InteractiveShellABC, ExecutionInfo, ExecutionResult
from IPython.core.magic import magics_class, line_magic, Magics
from ipykernel.zmqshell import ZMQInteractiveShell, KernelMagics
from ipykernel.ipkernel import IPythonKernel
from IPython.core.error import UsageError
from IPython import embed
from typing import List as ListType
from ast import AST
from traitlets import (
    Instance, Type, Dict, CBool, CBytes, Any, default, observe
)
import sys, ast, json, socket, pygments
from pygments.lexers import get_lexer_by_name
from pygments.formatters import Terminal256Formatter
def _doc_copy(from_func):
    def result(to_func):
        to_func.__doc__ = "copy of: " + from_func.__doc__
        return to_func
    return result

def ast2dict(node):
    if type(node) == list:
        return [ast2dict(n) for n in node]
    if not (hasattr(node,"__module__") and node.__module__ == "_ast"):
        return {"term":node}
    result = {attr:getattr(node,attr) for attr in node._attributes}
    result["ntype"] = type(node).__name__
    result["fields"] = dict([])
    for field_name in node._fields:
        child = getattr(node,field_name)
        result["fields"][field_name] = ast2dict(child)
    return result
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

def sendall_addr(sock, target_addr, msg, csize = 1024):
    if not msg.endswith(b"\0"):
        msg += b"\0"
    while msg:
        send, left = msg[:csize],msg[csize:]
        sock.sendto(send,target_addr)
        msg = left
def recvall(target):
    received = b""
    while True:
        data, client = target.recvfrom(4096)
        received += data
        if received.endswith(b"\0"):
            break
    return received[:-1], client

def walk(node, indent=0, indent_size = 4):
    if type(node) == str:
        node = ast.parse(node)
    # 入れ子構造をインデントで表現する
    print(' ' * indent, end='')

    # クラス名を表示する
    print(node.__class__, end=':')

    '''# 行数の情報があれば表示する
    if hasattr(node, 'lineno'):
        msg = ': {lineno}'.format(lineno=node.lineno)
        print(msg, end='')
    '''
    print(node._fields,end=':')

    # name,idがあれば表示する
    show = ["name", "id", "n", "s"]
    for i in show:
        if i in node._fields:
            print()
            print(" "*(indent+indent_size),getattr(node,i),end=':')

    # 改行を入れる
    print()

    # 再帰的に実行する
    for child in ast.iter_child_nodes(node):
        walk(child, indent=indent+indent_size, indent_size= indent_size)

@magics_class
class TransferKernelMagics(KernelMagics):
    @line_magic
    def setport(self, arg_s):
        if not arg_s:
            raise UsageError("Missing port num")
        arg_l = arg_s.split()
        if len(arg_l) == 1:
            arg_l = ["code"] + arg_l

        target, port = arg_l
        if target == "code":
            self.shell.code_port = int(port)
            print("code port is set to {0}".format(self.shell.code_port))
        else:
            raise UsageError("Unknown target port name: {0}".format(target))
    @line_magic
    def getport(self, arg_s):
        arg_l = arg_s.split()
        if len(arg_l) == 0:
            arg_l = ["code"] + arg_l

        target = arg_l[0]
        if target == "code":
            print("code port is {0}".format(self.shell.code_port))
        else:
            raise UsageError("Unknown target port name: {0}".format(target))
    @line_magic
    def printself(self, arg_s):
        print(list(arg_s))

class TransferInteractiveShell(ZMQInteractiveShell):
    banner = "transfers code to a different server"
    target_host = "localhost"
    code_port = 8887
    socket_timeout = 0.5

    @_doc_copy(ZMQInteractiveShell.run_ast_nodes)
    def run_ast_nodes(self, nodelist:ListType[AST], cell_name:str, interactivity='last_expr',
                        compiler=compile, result=None):
        if not nodelist:
            return
        try:
            has_exc = self.transfer_nodelist(nodelist, result, cell_name)
            if result.result is not None:
                out_result ="{0}".format(result.result)
                try:
                    if type(result.result) == str:
                        raise
                    mod = ast.Interactive([ast.parse(out_result).body[0]])
                    exec(compiler(mod,"ev", "single"))
                except:
                    out_result = r"'{0}'".format(str(result.result).replace("\\","\\\\").replace("'", "\\'"))
                    mod = ast.Interactive([ast.parse(out_result).body[0]])
                    exec(compiler(mod,"ev", "single"))

            if has_exc:
                return True
        except:
            if result:
                result.error_before_exec = sys.exc_info()[1]
            self.showtraceback()
            return True
        return False
    def transfer_nodelist(self, nodelist, result, cell_name):
        mod = ast.Module(nodelist)
        json_ast = json.dumps({"code":ast2dict(mod),"cell_name":cell_name})
        server_address = (self.target_host,self.code_port)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sendall_addr(sock,server_address, json_ast.encode("utf-8"))
            received, _ = recvall(sock)
        received = json.loads(received.decode("utf-8"))
        if received["out"]:
            if received["out"].endswith("\n"):
                received["out"]  = received["out"][:-1]
            print(received["out"])
        if received["exc"]:
            lexer = get_lexer_by_name("ipython3")

            formatter = Terminal256Formatter(style="default")
            print(pygments.highlight(received["exc"],lexer,formatter))
            result.error_in_exec = received["exc"]
            return True
        result.result = received["evl"]
        return False

    def init_magics(self):
        super(TransferInteractiveShell, self).init_magics()
        self.register_magics(TransferKernelMagics)

class ITransferKernel(IPythonKernel):
    shell_class = Type(TransferInteractiveShell)
    implementation = "ITransfer"
    implementation_version = "0.1"

InteractiveShellABC.register(TransferInteractiveShell)
if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(
        kernel_class=ITransferKernel)
