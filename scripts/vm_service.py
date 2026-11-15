"""Fixed active-role start/status/stop/restart; no arbitrary command or checkout."""
import argparse
import json
import socket
from scripts.vm_deploy import VM,DeployError
from scripts.vm_workspace import WorkspaceDeploymentError
from common.workspace_lifecycle import WorkspaceBusy


def control(vm,action,expected=None):
    with vm.lock():
        return vm.service_control(action,expected)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','status','stop','restart'))
    parser.add_argument('--expected')
    args=parser.parse_args()
    try:
        result=control(VM(socket.gethostname().removeprefix('security-')),args.action,args.expected)
        print(json.dumps({'ok':True,**result},indent=2))
    except (DeployError,WorkspaceBusy,WorkspaceDeploymentError) as exc:
        print(json.dumps({'ok':False,'reason_code':str(exc)}));raise SystemExit(2)


if __name__=='__main__':main()
