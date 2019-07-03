#! /usr/bin/python

import subprocess, shlex, logging, sys, getopt, time
from subprocess import call
import socket
import os, os.path, random

def run_cmd(cmd, cleanup=None):
	#args = shlex.split(cmd)
	try:
		output = subprocess.check_output(cmd, shell=True)
	except subprocess.CalledProcessError as e:
		print e.output
		if cleanup is not None:
			cleanup()
		sys.exit("cmd: " + cmd)
	return output

class check_mem_usage():
	def __init__(self, args=[]):
		mlnx_dev = "mlx5_dev"
		num_vf = 0
		server = False
		num_rules = 0
		try:
			opts, args = \
				getopt.getopt(args,"hi:n:s:r:",
					["interface=", "num_vf=", "server=", "num_rules="])
		except getopt.GetoptError:
			print 'mem_usage.py -i <interface> -n <num_vf> -s <0|1> -r <num_rules>'
			sys.exit(1)
		for opt, arg in opts:
			if opt == '-h':
				print ('mem_usage.py -i <interface> -n <num_vf> \
						-s <0|1> -r <num_rules>')
				sys.exit()
			elif opt in ("-i", "--interface"):
				mlnx_dev = arg
			elif opt in ("-n", "--num_vf"):
				num_vf = int(arg)
			elif opt in ("-s", "--server"):
				server = bool(int(arg))
			elif opt in ("-r", "--num_rules"):
				num_rules= int(arg)

		logging.basicConfig()
		logger = logging.getLogger("mem_check")
		logger.setLevel(logging.DEBUG)

		rep_test = check_rep_mem(logger, mlnx_dev,server, num_vf)
		rep_test.run()


class check_rep_mem():
	def __init__(self, log, mlx5_dev, server=True, num_vf=1):
		self.logger= log
		self.mlnx_dev = mlx5_dev
		self.server = server
		self.num_vf = num_vf
		self.host = '192.168.100.2'
		self.port = 5000
		self.dmesg_file = "/tmp/page_usage"
		self.page_file = "/tmp/give_page"

	def find(self, substr, infile, outfile):
		with open(infile) as a, open(outfile, 'w') as b:
			for line in a:
				if substr in line:
					b.write(line)

	def find_count(self, substr, infile):
		count = 0
		pos_count = 0
		neg_count = 0
		with open(infile) as file:
			for line in file:
				words = line.split()
				count = int(words[words.index(substr) + 1])
				if (count >= 0):
					pos_count += count
				else:
					neg_count += count
		self.logger.debug("Given: %d, Claim: %d", pos_count, neg_count)
		return pos_count + neg_count

	def clean_up(self):
		return

	def check_rep_cmd(self, cmd):
		return run_cmd(cmd, self.clean_up)

	def start_record_dmesg(self):
		cmd = ("dmesg > " + self.dmesg_file + " &")
		self.logger.debug("Saving dmesg to %s", self.dmesg_file)
		self.check_rep_cmd(cmd)
		self.check_rep_cmd("dmesg -C")

	def server_bringup_rep(self):
		self.check_rep_cmd("ifconfig rep0-1 up")
		time.sleep(3)
		self.logger.info("Bringup rep0-1")

	def check_rep(self):
		# Wait for host VF to reset
		self.start_record_dmesg()
		#self.server_bringup_rep()

		self.find("npages", self.dmesg_file, self.page_file)
		page_used = self.find_count("npages", self.page_file)
		fw_mem_used = page_used * 4 / 1024

		self.logger.info("-----------------------------------------")
		self.logger.info("\tFirmware Page:\t\t%d", page_used)
		self.logger.info("\tFirmware Memory:\t%d MB", fw_mem_used)
		self.logger.info("-----------------------------------------")

	def run(self):
		self.check_rep()

if __name__ == "__main__":
	test = check_mem_usage(sys.argv[1:])
	exit()
