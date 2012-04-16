# Authors:
#   Jason Gerard DeRose <jderose@redhat.com>
#
# Copyright (C) 2008  Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Various utility functions.
"""

import os
import imp
import time
import socket
import re
from types import NoneType
from weakref import WeakKeyDictionary

from ipalib import errors
from ipalib.text import _
from ipalib.dn import DN, RDN
from ipapython import dnsclient
from ipapython.ipautil import decode_ssh_pubkey


def json_serialize(obj):
    if isinstance(obj, (list, tuple)):
        return [json_serialize(o) for o in obj]
    if isinstance(obj, dict):
        return dict((k, json_serialize(v)) for (k, v) in obj.iteritems())
    if isinstance(obj, (bool, float, int, unicode, NoneType)):
        return obj
    if isinstance(obj, str):
        return obj.decode('utf-8')
    if not callable(getattr(obj, '__json__', None)):
        # raise TypeError('%r is not JSON serializable')
        return ''
    return json_serialize(obj.__json__())

def get_current_principal():
    try:
        # krbV isn't necessarily available on client machines, fail gracefully
        import krbV
        return unicode(krbV.default_context().default_ccache().principal().name)
    except ImportError:
        raise RuntimeError('python-krbV is not available.')
    except krbV.Krb5Error:
        #TODO: do a kinit?
        raise errors.CCacheError()

def get_fqdn():
    fqdn = ""
    try:
        fqdn = socket.getfqdn()
    except:
        try:
            fqdn = socket.gethostname()
        except:
            fqdn = ""
    return fqdn

# FIXME: This function has no unit test
def find_modules_in_dir(src_dir):
    """
    Iterate through module names found in ``src_dir``.
    """
    if not (os.path.abspath(src_dir) == src_dir and os.path.isdir(src_dir)):
        return
    if os.path.islink(src_dir):
        return
    suffix = '.py'
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(suffix):
            continue
        pyfile = os.path.join(src_dir, name)
        if os.path.islink(pyfile) or not os.path.isfile(pyfile):
            continue
        module = name[:-len(suffix)]
        if module == '__init__':
            continue
        yield (module, pyfile)


# FIXME: This function has no unit test
def load_plugins_in_dir(src_dir):
    """
    Import each Python module found in ``src_dir``.
    """
    for module in find_modules_in_dir(src_dir):
        imp.load_module(module, *imp.find_module(module, [src_dir]))


# FIXME: This function has no unit test
def import_plugins_subpackage(name):
    """
    Import everythig in ``plugins`` sub-package of package named ``name``.
    """
    try:
        plugins = __import__(name + '.plugins').plugins
    except ImportError:
        return
    src_dir = os.path.dirname(os.path.abspath(plugins.__file__))
    for name in find_modules_in_dir(src_dir):
        full_name = '%s.%s' % (plugins.__name__, name)
        __import__(full_name)


def make_repr(name, *args, **kw):
    """
    Construct a standard representation of a class instance.
    """
    args = [repr(a) for a in args]
    kw = ['%s=%r' % (k, kw[k]) for k in sorted(kw)]
    return '%s(%s)' % (name, ', '.join(args + kw))

def realm_to_suffix(realm_name):
    s = realm_name.split(".")
    terms = ["dc=" + x.lower() for x in s]
    return ",".join(terms)

def validate_host_dns(log, fqdn):
    """
    See if the hostname has a DNS A record.
    """
    rs = dnsclient.query(fqdn + '.', dnsclient.DNS_C_IN, dnsclient.DNS_T_A)
    if len(rs) == 0:
        log.debug(
            'IPA: DNS A record lookup failed for %s' % fqdn
        )
        raise errors.DNSNotARecordError()
    else:
        log.debug(
            'IPA: found %d records for %s' % (len(rs), fqdn)
        )

def isvalid_base64(data):
    """
    Validate the incoming data as valid base64 data or not.

    The character set must only include of a-z, A-Z, 0-9, + or / and
    be padded with = to be a length divisible by 4 (so only 0-2 =s are
    allowed). Its length must be divisible by 4. White space is
    not significant so it is removed.

    This doesn't guarantee we have a base64-encoded value, just that it
    fits the base64 requirements.
    """

    data = ''.join(data.split())

    if len(data) % 4 > 0 or \
        re.match('^[a-zA-Z0-9\+\/]+\={0,2}$', data) is None:
        return False
    else:
        return True

def validate_ipaddr(ipaddr):
    """
    Check to see if the given IP address is a valid IPv4 or IPv6 address.

    Returns True or False
    """
    try:
        socket.inet_pton(socket.AF_INET, ipaddr)
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, ipaddr)
        except socket.error:
            return False
    return True

def check_writable_file(filename):
    """
    Determine if the file is writable. If the file doesn't exist then
    open the file to test writability.
    """
    if filename is None:
        raise errors.FileError(reason='Filename is empty')
    try:
        if os.path.exists(filename):
            if not os.access(filename, os.W_OK):
                raise errors.FileError(reason=_('Permission denied: %(file)s') % dict(file=filename))
        else:
            fp = open(filename, 'w')
            fp.close()
    except (IOError, OSError), e:
        raise errors.FileError(reason=str(e))

def normalize_zonemgr(zonemgr):
    if not zonemgr:
        # do not normalize empty or None value
        return zonemgr
    if '@' in zonemgr:
        # local-part needs to be normalized
        name, at, domain = zonemgr.partition('@')
        name = name.replace('.', '\\.')
        zonemgr = u''.join((name, u'.', domain))

    if not zonemgr.endswith('.'):
        zonemgr = zonemgr + u'.'

    return zonemgr

def validate_dns_label(dns_label, allow_underscore=False):
    label_chars = r'a-z0-9'
    underscore_err_msg = ''
    if allow_underscore:
        label_chars += "_"
        underscore_err_msg = u' _,'
    label_regex = r'^[%(chars)s]([%(chars)s-]?[%(chars)s])*$' % dict(chars=label_chars)
    regex = re.compile(label_regex, re.IGNORECASE)

    if len(dns_label) > 63:
        raise ValueError(_('DNS label cannot be longer that 63 characters'))

    if not regex.match(dns_label):
        raise ValueError(_('only letters, numbers,%(underscore)s and - are allowed. ' \
                           '- must not be the DNS label character') \
                           % dict(underscore=underscore_err_msg))

def validate_domain_name(domain_name, allow_underscore=False):
    if domain_name.endswith('.'):
        domain_name = domain_name[:-1]

    domain_name = domain_name.split(".")

    # apply DNS name validator to every name part
    map(lambda label:validate_dns_label(label,allow_underscore), domain_name)

    if not domain_name[-1].isalpha():
        # see RFC 1123
        raise ValueError(_('top level domain label must be alphabetic'))

def validate_zonemgr(zonemgr):
    """ See RFC 1033, 1035 """
    regex_domain = re.compile(r'^[a-z0-9]([a-z0-9-]?[a-z0-9])*$', re.IGNORECASE)
    regex_local_part = re.compile(r'^[a-z0-9]([a-z0-9-_\.]?[a-z0-9])*$',
                                    re.IGNORECASE)

    local_part_errmsg = _('mail account may only include letters, numbers, -, _ and a dot. There may not be consecutive -, _ and . characters')

    if len(zonemgr) > 255:
        raise ValueError(_('cannot be longer that 255 characters'))

    if zonemgr.endswith('.'):
        zonemgr = zonemgr[:-1]

    if zonemgr.count('@') == 1:
        local_part, dot, domain = zonemgr.partition('@')
        if not regex_local_part.match(local_part):
            raise ValueError(local_part_errmsg)
        if not domain:
            raise ValueError(_('missing address domain'))
    elif zonemgr.count('@') > 1:
        raise ValueError(_('too many \'@\' characters'))
    else:
        last_fake_sep = zonemgr.rfind('\\.')
        if last_fake_sep != -1: # there is a 'fake' local-part/domain separator
            sep = zonemgr.find('.', last_fake_sep+2)
            if sep == -1:
                raise ValueError(_('missing address domain'))
            local_part = zonemgr[:sep]
            domain = zonemgr[sep+1:]

            if not all(regex_local_part.match(part) for part in local_part.split('\\.')):
                raise ValueError(local_part_errmsg)
        else:
            local_part, dot, domain = zonemgr.partition('.')

            if not regex_local_part.match(local_part):
                raise ValueError(local_part_errmsg)

    validate_domain_name(domain)

def validate_hostname(hostname, check_fqdn=True, allow_underscore=False):
    """ See RFC 952, 1123

    :param hostname Checked value
    :param check_fqdn Check if hostname is fully qualified
    """
    if len(hostname) > 255:
        raise ValueError(_('cannot be longer that 255 characters'))

    if hostname.endswith('.'):
        hostname = hostname[:-1]

    if '.' not in hostname:
        if check_fqdn:
            raise ValueError(_('not fully qualified'))
        validate_dns_label(hostname,allow_underscore)
    else:
        validate_domain_name(hostname,allow_underscore)

def validate_sshpubkey(ugettext, pubkey):
    try:
        algo, data, fp = decode_ssh_pubkey(pubkey)
    except ValueError:
        return _('invalid SSH public key')

def output_sshpubkey(ldap, dn, entry_attrs):
    if 'ipasshpubkey' in entry_attrs:
        pubkeys = entry_attrs.get('ipasshpubkey')
    else:
        entry = ldap.get_entry(dn, ['ipasshpubkey'])
        pubkeys = entry[1].get('ipasshpubkey')
    if pubkeys is None:
        return

    fingerprints = []
    for pubkey in pubkeys:
        try:
            algo, data, fp = decode_ssh_pubkey(pubkey)
            fp = u':'.join([fp[j:j+2] for j in range(0, len(fp), 2)])
            fingerprints.append(u'%s (%s)' % (fp, algo))
        except ValueError:
            pass
    if fingerprints:
        entry_attrs['sshpubkeyfp'] = fingerprints

def normalize_sshpubkeyfp(value):
    value = value.split()[0]
    value = unicode(c for c in value if c in '0123456789ABCDEFabcdef')
    return value

class cachedproperty(object):
    """
    A property-like attribute that caches the return value of a method call.

    When the attribute is first read, the method is called and its return
    value is saved and returned. On subsequent reads, the saved value is
    returned.

    Typical usage:
    class C(object):
        @cachedproperty
        def attr(self):
            return 'value'
    """
    __slots__ = ('getter', 'store')

    def __init__(self, getter):
        self.getter = getter
        self.store = WeakKeyDictionary()

    def __get__(self, obj, cls):
        if obj is None:
            return None
        if obj not in self.store:
            self.store[obj] = self.getter(obj)
        return self.store[obj]

    def __set__(self, obj, value):
        raise AttributeError("can't set attribute")

    def __delete__(self, obj):
        raise AttributeError("can't delete attribute")

# regexp matching signed floating point number (group 1) followed by
# optional whitespace followed by time unit, e.g. day, hour (group 7)
time_duration_re = re.compile(r'([-+]?((\d+)|(\d+\.\d+)|(\.\d+)|(\d+\.)))\s*([a-z]+)', re.IGNORECASE)

# number of seconds in a time unit
time_duration_units = {
    'year'    : 365*24*60*60,
    'years'   : 365*24*60*60,
    'y'       : 365*24*60*60,
    'month'   : 30*24*60*60,
    'months'  : 30*24*60*60,
    'week'    : 7*24*60*60,
    'weeks'   : 7*24*60*60,
    'w'       : 7*24*60*60,
    'day'     : 24*60*60,
    'days'    : 24*60*60,
    'd'       : 24*60*60,
    'hour'    : 60*60,
    'hours'   : 60*60,
    'h'       : 60*60,
    'minute'  : 60,
    'minutes' : 60,
    'min'     : 60,
    'second'  : 1,
    'seconds' : 1,
    'sec'     : 1,
    's'       : 1,
}

def parse_time_duration(value):
    '''

    Given a time duration string, parse it and return the total number
    of seconds represented as a floating point value. Negative values
    are permitted.

    The string should be composed of one or more numbers followed by a
    time unit. Whitespace and punctuation is optional. The numbers may
    be optionally signed.  The time units are case insenstive except
    for the single character 'M' or 'm' which means month and minute
    respectively.

    Recognized time units are:

        * year, years, y
        * month, months, M
        * week, weeks, w
        * day, days, d
        * hour, hours, h
        * minute, minutes, min, m
        * second, seconds, sec, s

    Examples:
        "1h"                    # 1 hour
        "2 HOURS, 30 Minutes"   # 2.5 hours
        "1week -1 day"          # 6 days
        ".5day"                 # 12 hours
        "2M"                    # 2 months
        "1h:15m"                # 1.25 hours
        "1h, -15min"            # 45 minutes
        "30 seconds"            # .5 minute

    Note: Despite the appearance you can perform arithmetic the
    parsing is much simpler, the parser searches for signed values and
    adds the signed value to a running total. Only + and - are permitted
    and must appear prior to a digit.

    :parameters:
        value : string
            A time duration string in the specified format
    :returns:
        total number of seconds as float (may be negative)
    '''

    matches = 0
    duration = 0.0
    for match in time_duration_re.finditer(value):
        matches += 1
        magnitude = match.group(1)
        unit = match.group(7)

        # Get the unit, only M and m are case sensitive
        if unit == 'M':         # month
            seconds_per_unit = 30*24*60*60
        elif unit == 'm':       # minute
            seconds_per_unit = 60
        else:
            unit = unit.lower()
            seconds_per_unit = time_duration_units.get(unit)
            if seconds_per_unit is None:
                raise ValueError('unknown time duration unit "%s"' % unit)
        magnitude = float(magnitude)
        seconds = magnitude * seconds_per_unit
        duration += seconds

    if matches == 0:
        raise ValueError('no time duration found in "%s"' % value)

    return duration

def gen_dns_update_policy(realm, rrtypes=('A', 'AAAA', 'SSHFP')):
    """
    Generate update policy for a DNS zone (idnsUpdatePolicy attribute). Bind
    uses this policy to grant/reject access for client machines trying to
    dynamically update their records.

    :param realm: A realm of the of the client
    :param rrtypes: A list of resource records types that client shall be
                    allowed to update
    """
    policy_element = "grant %(realm)s krb5-self * %(rrtype)s"
    policies = [ policy_element % dict(realm=realm, rrtype=rrtype) \
               for rrtype in rrtypes ]
    policy = "; ".join(policies)
    policy += ";"

    return policy

def validate_rdn_param(ugettext, value):
    try:
        rdn = RDN(value)
    except Exception, e:
        return str(e)
    return None

def validate_dn_param(ugettext, value):
    try:
        rdn = DN(value)
    except Exception, e:
        return str(e)
    return None
