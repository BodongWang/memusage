#! /usr/bin/python

import subprocess, shlex, logging, sys
from subprocess import call

class check_mem_usage():
	def __init__(self, args=[]):
		logger = logging.getLogger()
		logger.setlevel(logging.info)

	def run_cmd(self, cmd)
		args = shlex.split(cmd)
		return subprocess.check_output(args)

	def start_mst(self)
		cmd = "mst start"
		run_cmd(cmd)

	def setup_vf(self):
		get_num_vf = "mlxconfig -d /dev/mst/mt41682_pciconf0 q | grep NUM_OF_VFS"
		num_vf = run_cmd(get_num_vf).split()[1]
		logger.info("num of vf: %d", num_vf)

	def run(self):
		start_mst()
		setup_vf()

if __name__ == "__main__":
	test = check_mem_usage(sys.argv[1:])
	test.run()
