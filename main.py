#!/usr/bin/python
import os, json, re, shutil, sys
from hashlib import md5
from bottle import route, run, static_file, request, response, get, error, HTTPError, HTTPResponse
from jinja2 import Environment, PackageLoader
tenv = Environment(loader=PackageLoader(__name__, "templates"))

aroot = os.path.dirname(__file__)
ccdata_root = sys.argv[1]

def abort(code, err=''):
	if request.content_type == 'text/html':
		raise HTTPError(code, err)
	else:
		raise HTTPResponse(err, status = code)

def file_route(mth):
	def dec(f):
		@route('/ajax/computer/<cid>/<pth:path>', method=mth)
		def newf(*a, **k):
			cid = k.get('cid')
			path = k.get('pth')
			
			comp_pth = os.path.join(ccdata_root, cid)
	
			if os.path.isdir(comp_pth):
				if not check_auth(comp_pth, [request.params.pw]):
					abort(401, 'Access Denied')
			else:
				abort(404, 'Could not find computer with the specified id')
			
			if path == None:
				return f(comp_pth, comp_pth)
			elif check_relpath(path):
				return f(comp_pth, os.path.join(comp_pth, path))
			abort(400, 'The requested file is protected')
			
		return newf
	return dec

def check_auth(fdir, poss):
	pwd_fl = os.path.join(fdir, ".password")
	if os.path.isfile(pwd_fl):
		with open(pwd_fl, 'r') as opwd_fl:
			for pw in opwd_fl:
				if pw.strip() != '' and pw.strip() in poss:
					return True
	return False

def check_relpath(rpth):
	npth = os.path.normpath(rpth)
	if npth in ['.password']:
		return False
	return True

types = {
	'lua': {
		'exts': ['.lua', ''],
		'names': [],
		'icon': 'script.png',
		'aceMode': 'lua',
	},
	'txt': {
		'exts': ['.txt'],
		'icon': 'page_white_text.png',
	},
	'log': {
		'exts': ['.log'],
		'icon': 'script_lightning.png',
	},
	
	'locked': {
		'names': ['.password'],
		'icon': 'page_white_key.png',
	},
	'folder': {
		'icon': 'folder.png',
		'aceMode': '',
	},
	'default': {
		'icon': 'page_white.png',
		'aceMode': 'text',
	},
}

# Gets type data for the file
def getType(fl):
	if os.path.isdir(fl):
		return types['folder']
	
	base = os.path.basename(fl)
	ext = os.path.os.path.splitext(fl)[1]
	for typn in types:
		typ = types[typn]
		if base in typ.get('names', []) or ext in typ.get('exts', []):
			ret = {}
			ret.update(types['default'])
			ret.update(typ)
			return ret
		
	return types['default']

# Get the label for the computer with the specified id
def get_label(cid):
	lfl = os.path.join(ccdata_root, 'labels.txt')
	if os.path.exists(lfl):
		with open(lfl, 'r') as olfl:
			for lbl in olfl:
				mtch = re.match('(\d*)\s(.*)', lbl)
				if mtch and mtch.group(1) == str(cid):
					return mtch.group(2)
	return '<i>Unnamed</i>'

# Creates a node descriptor to be sent to the client
def describe(ffl):
	fl = os.path.basename(ffl)
	typ = getType(ffl)
	return {
		'id': md5(ffl).hexdigest()[:16],
		'text': fl,
		'icon': os.path.join('/static/img/', typ['icon']),
		'children': os.path.isdir(ffl),
		'data': {
			'type': 'folder' if os.path.isdir(ffl) else 'file',
			'name': fl,
			'aceMode': 'ace/mode/' + typ['aceMode'],
		},
	}

@route("/")
def index():
	return tenv.get_template('index.html').render()

@route("/ajax/computer/")
def list_computer():
	comps = []
	
	for comp in sorted(os.listdir(ccdata_root)):
		cpath = os.path.join(ccdata_root, comp)
		if os.path.isdir(cpath) and comp.isdigit() and check_auth(cpath, [request.params.pw]):
			comps.append({
				'id': md5(cpath).hexdigest()[:16],
				'text': '%s: %s' % (comp, get_label(comp)),
				'icon': '/static/img/computer.png',
				'children': True,
				'state': {
					
				},
				'data': {
					'type': 'computer',
					'name': comp,
				}
			})
		
	response.content_type = 'application/json'
	return json.dumps(comps)

@get("/ajax/computer/<cid>")
@get("/ajax/computer/<cid>/")
@file_route('GET')
def open_file(comp_dir, jpth):
	if os.path.isdir(jpth):
		itms = []
		for fl in os.listdir(jpth):
			ffl = os.path.join(jpth, fl)
			itms.append(describe(ffl))
			
		response.content_type = 'application/json'
		return json.dumps(itms)
	else:
		with open(jpth, 'r') as fl:
			return fl.read()

@file_route('POST')
def save_file(comp_dir, ffl):
	if request.params.get('newname'):
		newloc = os.path.join(os.path.dirname(ffl), request.params.newname)
		if not os.path.exists(newloc):
			shutil.move(ffl, newloc)
			return describe(newloc)
		abort(400, 'Destination already exists')
	else:
		ptype = request.params.get('type')
		if ptype == 'file':
			if request.params.get('file_data'):
				with open(ffl, 'w') as fl:
					fl.write(request.params.file_data)
				return
			elif request.params.get('isnew'):
				if not os.path.exists(ffl):
					open(ffl, 'w').close()
					return describe(ffl)
				abort(400, 'File exists')
			abort(400, 'File contents not supplied')
		
		elif ptype == 'folder':
			if not os.path.exists(ffl):
				os.makedirs(ffl)
				return
			abort(400, 'Folder Exists')

	abort(400)

@file_route('DELETE')
def delete_file(comp_dir, ffl):
	if (ffl != comp_dir):
		if os.path.isdir(ffl):
			shutil.rmtree(ffl)
		elif os.path.isfile(ffl):
			os.remove(ffl)
		return
	
	abort(400)

@route('/static/<fl:path>')
def static_files(fl):
	return static_file(fl, root=os.path.join(aroot, "static"))
	
run(host='0.0.0.0', port=8000, reloader=True)