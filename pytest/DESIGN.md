# LISAv3 Technical Specification Document

This document outlines the technical specifications for LISAv3. We are
evaluating the feasibility of leveraging
[Pytest](https://docs.pytest.org/en/stable/) as our test runner.

Please see [PR #1065](https://github.com/LIS/LISAv2/pull/1065) for a working,
proof-of-concept prototype.

Authored by Andrew Schwartzmeyer (he/him), version 0.1.0.

## Why Pytest?

Pytest is an [incredibly popular](https://docs.pytest.org/en/stable/talks.html)
MIT licensed open source Python testing framework. It has a thriving community
and plugin framework, with over 750
[plugins](https://plugincompat.herokuapp.com/). Instead of writing (and
therefore maintaining) yet another test framework, we would do less with more by
reusing Pytest and existing plugins. This will allow us to focus on our unique
problems: organizing and understanding our tests, deploying necessary resources
(such as Azure or Hyper-V virtual machines), and analyzing our results.

In fact, most of Pytest itself is implemented via [built-in
plugins](https://docs.pytest.org/en/stable/plugins.html), providing us with many
useful and well-documented examples. Furthermore, when others were confronted
with a problem similar to our own they also chose to use Pytest.
[Labgrid](https://github.com/labgrid-project/labgrid) is an open source embedded
board control library that delegated the testing framework logic to Pytest in
their [design](https://labgrid.readthedocs.io/en/latest/design_decisions.html),
and [U-Boot](https://github.com/u-boot/u-boot), an embedded board boot loader,
similarly leveraged Pytest in their
[tests](https://github.com/u-boot/u-boot/tree/master/test/py). KernelCI and
Avocado were also evaluated by the Labgrid developers at an [Embedded Linux
Conference](https://youtu.be/S0EJJM5bVUY) and both ruled out for reasons similar
to our own before they settled on Pytest.

The [fundamental features](https://youtu.be/CMuSn9cofbI) of Pytest match our
needs very well:

* Automatic test discovery, no boiler-plate test code
* Useful information when a test fails (assertions are introspected)
* Test and fixture parameterization
* Modular setup/teardown via fixtures
* Incredibly customizable (as detailed above)

So all the logic for describing, discovering, running, skipping based on
requirements, and reporting results of the tests is already written and
maintained by the greater open source community, leaving us to focus on our hard
and specific problem: creating an abstraction to launch the necessary nodes in
our environments. Using Pytest would also allow us the space to abstract other
commonalities in our specific tests. In this way, LISAv3 could solve the
difficulties we have at hand without creating yet another test framework.

## High-Level Design Decisions

### What are the User Modes?

Because Pytest is infinitely customizable, we want to provide a few sets of
reasonable default configurations for some common scenarios. We will add a flag
like `--mode=[dev,debug,ci,demo]` to change the default options and output of
Pytest. Doing so is readily supported by Pytest via the `pytest_addoption` and
`pytest_configure` hooks. We call these the provided “user modes.”

* The dev(eloper) mode is intended for use by test developers while writing a
  new test. It is verbose, caches the deployed VMs between runs, and generates a
  digestible [HTML](https://pypi.org/project/pytest-html/) report.

* The debug mode is like dev mode but with all possible information shown, and
  will open the Python debugger automatically on failures (which is provided by
  Pytest with the `--pdb` flag).

* The CI mode will be fairly quiet on the console, showing all test results, but
  putting the full info output into the generated report file (HTML for sharing
  with humans and
  [JUnit](https://docs.pytest.org/en/stable/_modules/_pytest/junitxml.html) for
  the associated CI environment, which presents as native test results).

* The demo mode will show the “executive summary” (a lot like CI, but finely
  tuned for demos). For example, what `make smoke` currently shows.

### How Are Tests Described?

The built-in [pytest-mark](https://docs.pytest.org/en/stable/mark.html) plugin
already provides functionality for adding metadata to tests, where we
specifically want:

* Platform: used to skip tests inapplicable to the current system-under-test
* Category: our high-level test organization
* Area: feature being tested (could default to module name)
* Priority: self-explanatory
* Tags: optional additional metadata for test organization

We simply reuse this with minimal logic to enforce our required metadata, with
sane defaults (perhaps setting the area to the name of the module), and to list
statistics about our test coverage. This is already included in the prototype.
It looks like this:

```python
import pytest

@pytest.mark.lisa(
    platform="Azure", category="Functional", area="LIS_DEPLOY", priority=0, tags=["lis"]
)
def test_lis_driver_version(node: Node) -> None:
    """Checks that the installed drivers have the correct version."""
    ...
```

This is a functional example, which takes zero implementation. With this simple
decorator, all test collection hooks can introspect the metadata, enforce
required parameters and set defaults, select tests based on arbitrary criteria,
and list test coverage statistics.

Note that Pytest leverages Python’s docstrings for built-in documentation (and
can even run tests discovered in such strings, like doctest). Being just Python
code, this decorator need not be `@pytest.mark.lisa(...)` but can trivially be
provided as simply `@lisa(...)`.

This mark also does need to be repeated for each test, as marks can be scoped to
a module, and so one line could describe defaults for every test in a file, with
individual tests overriding parameters as needed. We may also introduce marks
such as `@pytest.mark.slow` to allow for easier test selection.

We even have a prototype
[generator](https://github.com/LIS/LISAv2/tree/pytest/generator) which parses
LISAv2 XML test descriptions and generates stubs with this mark filled in
correctly.

### How Are Tests Selected?

Pytest already allows a user to specify which exact tests to run:

* Listing folders on the CLI (see below on where tests should live)
* Specifying a name expression on the CLI (e.g. `-k smoke and xdp`)
* Specifying a mark expression on the CLI (e.g. `-m functional and not slow`)

We can also implement any other mechanism via the
`pytest_collection_modifyitems` hook. There’s already a
[proof-of-concept](https://github.com/LIS/LISAv2/blob/ab01c33f1f1e1ffac7100f6a69beda07192f05bb/pytest/conftest.py#L49)
which uses selection criteria read from a YAML file:

```yaml
# Select all Priority 0 tests
- criteria:
    priority: 0
# Exclude all tests in Area "xdp"
- criteria:
    area: xdp
  select_action: forceExclude
# Run test with name `test_smoke` twice
- criteria:
    name: test_smoke
  times: 2
```

However, before we settle on the basic schema understood by the
proof-of-concept, we should write and _review_ a full schema.

### How Are Results Reported?

Parsing the results of a large test suite can be difficult. Fortunately, because
Pytest is a testing framework, there already exists support for generating
excellent reports. For developers, the
[HTML](https://pypi.org/project/pytest-html/) report is easy to read: it is
self-contained, holds all the results and logs, and each test can be expanded
and collapsed. Tests which were rerun are recorded separately. For CI pipelines,
Pytest has integrated
[JUnit](https://docs.pytest.org/en/stable/_modules/_pytest/junitxml.html) XML
test report support. This is the standard method of reporting results to CI
servers like Jenkins and are natively parsed into the CI system’s built-in test
display page. Finally, Azure DevOps pipelines are even supported with a
community plugin
[pytest-azurepipelines](https://pypi.org/project/pytest-azurepipelines/) which
enhances the standard JUnit report for ADO.

### How Are Nodes Provided and Accessed?

First we need to define “node” as an instance of a system-under-test. That is,
given some environment requirements, such an Azure image (URN) and image (SKU),
a node would be a virtual machine deployed by Pytest with SSH access provided to
the tests. A node could optionally be deployed outside Pytest.

Pytest uses [fixtures](https://docs.pytest.org/en/stable/fixture.html), which
are the primary way of setting up test requirements. They replace less flexible
alternatives like setup/teardown functions. It is through fixtures that we
implement remote node setup/teardown. Our node fixture currently provides:

* Automatic provisioning of an Azure VM given URN and SKU
* Remote shell access via SSH
* Data including hostname / IP address for local tools
* Cross-platform ping functionality with exponential back-off
* Allowing ICMP ping via Azure firewall rules
* Platform API reboot
* Uploading of local files to arbitrary remote destinations
* Downloading of remote file contents into local string variable
* Downloading boot diagnostics (serial console log) from platform
* Asynchronous remote command execution with promises

The prototype demonstrates how easy it is to quickly implement these features.
As we need more features, they can be readily added and shared among tests.

Our abstraction leverages [Fabric](https://www.fabfile.org/) which is a popular
high-level Python library for executing shell commands on remote systems over
SSH. Underneath the covers it uses
[paramiko](https://docs.paramiko.org/en/stable/), the most popular low-level
Python SSH library. Fabric does the heavy lifting of safely connecting and
disconnecting from the node, executing the shell command (synchronously or
asynchronously), reporting the exit status, gathering the stdout and stderr,
providing stdin (or interactive auto-responses, similar to `expect`), uploading
and downloading files, and much more. In fact, these APIs are all available and
implemented for the local machine by the underlying
[Inovke](https://www.pyinvoke.org/) library, which is essentially a Python
`subprocess` wrapper with “a powerful and clean feature set.”

Other test specific requirements, such as installing software and daemons,
downloading files from remote storage, or checking the state of our Bash test
scripts, would similarly be implemented by methods on the `Node` class or via
additional fixtures and thus shared among tests.

For Azure, we use the [Azure CLI](https://aka.ms/azureclidocs) to deploy a
virtual machine. For Hyper-V (and other virtualization platforms), we would like
to use [libvirt](https://libvirt.org/python.html), and for embedded
environments we are evaluating
[labgrid](https://github.com/labgrid-project/labgrid).

Tests do not need to explicitly call for a node to be provided, and we do not
need to write much code to setup this resource-provider logic. We simply define
a `Node` class and a Pytest fixture which returns one:

```python
@pytest.fixture(scope="session")
def node(request: FixtureRequest) -> Iterator[Node]:
    """Return the current node for any test which requests it."""
    with Node(<URN, SKU, etc.>) as n:
        yield n

@pytest.mark.lisa(...)
def test_uptime(node: Node) -> None
    """Automatically has access to the current node because of the argument."""
    # Runs `uname` via SSH and asserts it's Linux.
    assert node.run("uname").stdout.strip() == "Linux"
```

When created, the `Node` instance either uses a cached node or deploys a new one
based on the given parameters (which can be provided at runtime). When the scope
of the fixture is exited (in this example, the test session), the `Node`
instance deletes its deployed resource unless requested not to by the user,
which is currently controlled by the `--keep-vms` flag.

To provide the parameters to the node fixture, the prototype currently
implements a simple `@pytest.mark.deploy(...)` mark which takes `vm_image`,
`vm_size`, etc., and it’s applied to each function. This worked for the demo,
and proved the concept; however, we will want to provide a mechanism for
specifying lists of environments and their required resources to the tests at
runtime. This will likely be a YAML file that is parsed at initialization and
used to parameterize the node fixture itself, causing all the tests to be
executed for each environment. For more details, see the section “Where Does
Parameterization Happen?”

See the Detailed Design Decisions below for what the `Node` class looks like.

#### Interaction with Azure

We do not use the [Azure Python APIs](https://aka.ms/azsdk/python/all) directly
because they are more complicated (and less documented) than the [Azure
CLI](https://aka.ms/azureclidocs). With Invoke (as discussed above), `az`
becomes incredibly easy to work with. The Azure CLI lead developer states that
they have [feature parity](https://stackoverflow.com/a/50005660/1028665) and
that the CLI is more straightforward to use. Considering our ease-of-maintenance
requirement, this seems the apt choice. If it later becomes necessary to use the
Python APIs directly, that is, of course, still allowed by our design.

### How Are Tests Timed Out?

The [pytest-timeout](https://pypi.org/project/pytest-timeout/) plugin provides
integrated timeouts via `@pytest.mark.timeout(<N seconds>)`, a configuration
file option, environment variable, and CLI flag. The Fabric library provides
timeouts in both the configuration and per-command usage. These are already used
to satisfaction in the prototype.

### How Are Tests Organized?

That is, what does a folder of tests map to: a platform, feature, or owner?

In my opinion it is likely to be both. Tests which are common to a platform and
written by our team are probably best placed in a folder like `tests/azure`
whereas tests for a particular scenario which limits their image and SKU
applicability should be in a folder like `tests/acc`. It’s going to depend on
how often the tests are run together.

Because Pytest can run tests and `conftest.py` files from arbitrary folders,
maintaining sets of tests and plugins separately from the base LISA repository
is easy. Custom repositories with new tests, plugins, fixtures,
platform-specific support, etc. can simply be cloned anywhere, and provided on
the command-line to Pytest.

Test authors should keep tests which share requirements and are otherwise
similar to a single module (Python file). Not only is this well-organized, but
because marks can be applied at the module level, setting all the tests to be
skipped or expected to fail (with the built-in `skip` and `xfail` Pytest marks)
becomes even easier.

An open question is if we really want to bring every test from LISAv2 directly
over, or if we should carefully analyze our tests to craft a new set of
high-level scenarios. An interesting result of reorganizing and rewriting the
tests would be the ability to have test layers, where the result of a high-level
test dictates if the tests below it should be skipped. If it passes, it implies
the tests underneath it would pass, and so skips them; but if it fails, the next
test below it runs and so on until a passing layer is found.

### How Will We Port LISAv2 Tests?

Given the above, we still must decide if we want to put the engineering effort
into porting _every_ LISAv2 test. However, the prototype started by porting the
`LIS-DRIVER-VERSION-CHECK` test, proving that tests which exclusively use Bash
scripts are trivially portable. Unfortunately, most tests use an associated
PowerShell script which is tightly coupled to the LISAv2 framework.

We believe that it is _possible_ to port these tests without untoward
modifications. We would need to write a mock library that implements (or stubs
where appropriate) LISAv2 framework functionality such as
`Provision-VMsForLisa`, `Copy-RemoteFiles`, `Run-LinuxCmd`, etc., and provides
both the expected “global” objects and the test function parameters `AllVmData`
and `CurrentTestData`.

This work needs to be done regardless of the approach we take with our framework
(leveraging Pytest or writing our own), and it is not inconsequential work. It
needs to be thoroughly planned and executed, and is certainly a ways off.

### What Do Parallel Tests Mean?

While our original list of goals stated that we want to run tests “in parallel”
we were not specific about what was meant, and the topic of parallelism and
concurrency is understandably complex. We certainly don’t mean running two tests
at once on the same node, as this would undoubtedly lead to flaky tests.

Assuming that we care about a set of tests passing on a particular image and
size combination, but not necessarily on a particular deployed instance, then we
can run tests concurrently by deploying multiple “identical” nodes and splitting
the tests across them. The tests would still run in isolation on each node. This
sounds hard, but actually it’s practically free with Pytest if the node fixture
is session scoped and we use
[pytest-xdist](https://pypi.org/project/pytest-xdist/) as described below.

It’s also unlikely that we want to write our tests using the Async I/O pattern,
because we do not want tests to accidentally conflict with each other. While
[pytest-asyncio](https://pypi.org/project/pytest-asyncio/) exists, our
concurrency model is probably as described above: split the tests among multiple
identical nodes.

### How Are Tests and Functions Retried?

Testing remote instances is inherently flaky, so we take a two-pronged approach
to dealing with the flakiness.

The [pytest-rerunfailures](https://pypi.org/project/pytest-rerunfailures/)
plugin will be used to easily mark a test itself as flaky. It has the nice
feature of recording each rerun in the produced report. It looks like this:

```python
@pytest.mark.flaky(reruns=5)
def test_something_flaky(...):
    """This fails most of the time."""
    ...
```

> Note that there is an open
> [bug](https://github.com/pytest-dev/pytest-rerunfailures/issues/51) in this
> plugin which can cause issues with fixtures using scopes other than “function”
> but it can be worked around.

The [Tenacity](https://tenacity.readthedocs.io/en/latest/) library should be
used to retry flaky functions that are not tests, such as downloading boot
diagnostics or pinging a node. As the modern Python retry library it has
easy-to-use decorators to retry functions (and context managers to use within
functions), as well as excellent wait and timeout support. It looks like this:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class Node:
    ...
    @retry(reraise=True, wait=wait_exponential(), stop=stop_after_attempt(3))
    def ping(self, **kwargs):
        """Ping the node from the local system in a cross-platform manner."""
        flag = "-c 1" if platform.system() == "Linux" else "-n 1"
        return self.local(f"ping {flag} {self.host}", **kwargs)
    ...
```

We can additionally list a test twice when modifying the items collection, as
implemented in the criteria proof-of-concept. However, given the above
abilities, this may not be desired.

### Where Does Parameterization Happen?

Do we parameterize
[tests](https://docs.pytest.org/en/stable/parametrize.html#parametrizemark) or
[fixtures](https://docs.pytest.org/en/stable/fixture.html#fixture-parametrize)?

This all comes down to how we want to use LISA. If we want to put a single
system under test at a time, and run all possible tests against it, then it
would make sense to parameterize the node fixture across the set of images to
test. I believe this to likely be the case.

A parameterized node fixture would be session-scoped. This would enable us to
take advantage of [pytest-xdist](https://pypi.org/project/pytest-xdist/) for
running the tests concurrently against multiple nodes, where each forked runner
has its own node. Note that the cache key for deployed nodes will need to
include an identifier to separate the parallel runs, but this is available.

This approach would let us list a number of images and sizes (or a matrix
combination of them) and then run all requested tests against each of those.
However, it means that tests will need to be intelligent enough to [skip or
xfail](https://docs.pytest.org/en/stable/skipping.html) on systems where they do
not apply. This can be done in test code to start with. As commonalities are
realized they can be refactored into simple, reusable feature checks.

Finally, while the base (and most common) case of tests which require one node
becomes trivially solved, we still have to deal with the edge cases of tests
which use two or three nodes. Determining the best course of action here
requires investigating how and when those tests are run, and if the node pair or
triple all use the same image and size. An easy solution would be to have a test
which requires a second or third node to simply deploy them through a
function-scoped fixture, and tear them down at the end. This may be costly in
terms of time if there are many of these tests and they run frequently, but for
long “performance” tests it would be an adequate option. Alternatively, we could
have a node pool that the session-scoped node fixture uses, where each node is
locked while in use. While this would take more engineering effort, it means we
could use the nodes for running tests concurrently, and “borrow” a runner when a
test needs another.

Other ideas are welcome, but what we don’t want to do is change the environment
a user is expecting their tests to run in. I do not think that we should use a
“least common denominator” approach that collects feature requests and deploys
nodes which match those features, as the user will lose control over their
environment. We still want to enumerate features so tests can check if they’re
applicable, but the user’s environment request should be respected.

Alternatively, parameterizing tests means that each test (or module, or class,
as the fixture could no longer be session-scoped) specifies in some way (whether
in code or read at runtime from a file) what image/size combinations it should
run against. This generally eliminates having to check if it should skip, but
means that running the test suite will put multiple systems under test at once,
the results of which may be difficult to interpret. While this is a viable
route, it means maintaining a comprehensive list of which environments each
tests use, and I think feature-checking is more scalable.

This is an open question which we need to settle as the two methods can
technically be combined, but we will want to be careful if we do this.

Regardless of approach, we will want to write and _review_ a simple YAML schema
for specifying the system-under-test targets. As described above, the prototype
currently reads this information from a mark, but if we move forward with the
suggestion above, the scope of the node fixture will change to session and it
will become parameterized. Those parameters would be set at runtime by reading a
given YAML file.

### When Do We Export a Plugin?

The current prototype is simply using Pytest. All the implementation is in the files
`conftest.py` and `node_plugin.py`, the former of which is Pytest’s default
“user plugin” file. We likely want to create a proper `pytest-lisa` package
which provides our marks, fixtures, command-line parameters, user modes, and
hook modifications for reading YAML files.

This requires more research as doing so is obviously not necessary but is nice.

## Detailed Design Decisions

This section contains truly technical specifications of our current plans to
bring the prototype to production.

### Planned `Node` Class Refactor

#### Basic Shape

`Node` should still subclass `fabric.Connection`. It should be a partially
abstract class with platform-specific subclasses (Azure, libvirt, an embedded
device, etc.). However, the initializer and context manager methods _should not_
need to be reimplemented by a platform subclass. Most added methods like
`ping()` and `reboot()` should also be shared. This is where static type
checking will help.

An `Environment` class will be a collection of nodes in a group, for tests which
require multiple nodes. It is important that `Node` is self-contained and does
not require an `Environment` instance because the base case of most tests is to
use a `Node`.

#### Caching

A `Node` should be able to be cached. If `--keep-vms` is given to Pytest, it
should not delete the deployed VM resource and should instead cache its data so
that a subsequent invocation can connect directly to it. A `Node` should also be
able to connect directly to a system deployed outside Pytest, reusing the cache
hydration logic. The `init()` and `__exit__()` methods will handle checking and
updating the cache so that this logic is shared.

Note that cross-session [caching](https://docs.pytest.org/en/stable/cache.html)
is provided by Pytest, and very easy to work with. The existing prototype
already implements `--keep-vms`.

#### Initializing

The `init()` method does the following:

* Takes an optional group ID (provided by Environment for instance so that it’s
  easy to create/deploy multiple nodes into one group) to generate its name and
  deduce its group.

* Checks the cache for the node’s key.

* On a cache miss, calls `deploy()` and saves the returned host to the field
  inherited from `Connection` and the rest of the platform-specific information
  to a `data` dictionary field. Caches the data dictionary for the node’s key.

* On a cache hit, saves the cached host and data to the instance.

* Calls `super()` to setup `Connection` with our default Fabric configuration.

#### Deploy and Delete

* The `deploy()` and `delete()` methods are abstract and implemented by
  platform-specific node classes to actually deploy the VM. For Azure, note that
  `deploy()` will check if the resource group exists, and if not, creates it.
  For `delete()` it will check if it is the last VM in the group, and if so
  deletes the group too. Again this is to keep `Environment` from being a
  requirement.

* The group ID is `pytest-{uuid4()}` (maybe with `pytest` being replaced by a
  user- or run-specific short identifier). The ID should be returned by a static
  method so that when an `Environment` creates a collection of nodes, it can
  simply use the static method to generate a shared group ID.

* The context manager’s `__exit__()` method calls `super()` to disconnect and
  potentially `delete()` the VM. If it’s to be deleted, the key/value pair is
  also removed from the cache.

* Because of how Python’s context managers work, we may not need to reimplement
  `__enter__()` but will want to check its inherited implementation.

#### Common Tasks

Common tasks for systems under tests like rebooting and pinging should be
implemented on the `Node` class.

* Methods inherited from `Connection` include `run()`, `sudo()` and `local()`
  which are used to easily run arbitrary commands, and `get()` and `put()` to
  download and upload arbitrary files.

* The `cat()` method (already implemented in the prototype) wraps `get()` and
  returns the file as data in a string. This makes test code like this possible:

  ```python
  assert node.cat("state.txt") == "TestCompleted"
  ```

* Reboot should first try to use `self.sudo("reboot", timeout=5)` (with a short
  timeout to avoid a hung SSH session). It should retry with an exponential
  back-off to see if the machine has rebooted by checking either `uptime` or the
  existence of a file created before the reboot. This is to avoid having to
  `sleep()` and just guess the amount of time it takes to reboot.

* Restart should “power cycle” the machine using the platform’s API, and thus is
  in abstract method. It should optionally be able to redeploy the node too,
  which can be used by tests which require a completely fresh node.

* Note that the `local()` method is already overridden to patch Fabric so as to
  ignore the provided SSH environment. This demonstrates that we can easily
  provide necessary changes to users while still leveraging the library. For
  instance, we may want an alternative to `run()` which, instead of taking a
  string, takes a list of arguments and quotes them correctly so as to deal with
  difficult shell quoting edge cases.

* One new method we’ve already identified is `copy_scripts()` which will copy a
  list of scripts to the node and mark them executable. It could even be a
  context manager which deletes the scripts when exited.

## Alternatives Considered

### Writing Another Framework

I believe the above set of technical specifications clearly describes how we can
leverage Pytest for our needs. Furthermore, the existing prototype proves this
is a viable option. Therefore I do not think we should consider writing and
maintaining a _new_ Python testing framework. We should avoid falling for “not
invented here” syndrome. The alternative prototype which does implement a new
framework required over five thousand lines of code, the Pytest-based prototype
used less than two hundred, or less than three percent. We do not want to take
on the maintenance cost of yet another framework, the maintenance cost of LISAv2
already caused this mess in the first place. I think the work of prototyping
said new framework was valuable, as it provided insight into the eventual
technical design of LISAv3.

### Using Remote Capabilities of pytest-xdist

With the [pytest-xdist plugin](https://github.com/pytest-dev/pytest-xdist) there
already exists support for running a folder of tests on an arbitrary remote host
via SSH.

The LISA tests could be written as Python code suitable for running on the
target test system, which means direct access to the system in the test code
itself (subprocesses are still available, without having to use SSH within the
test, but would become far less necessary), something that is not possible with
any current prototype. Where the pytest-xdist plugin copies the package of code
to the target node and runs it, the pytest-lisa plugin could instantiate that
node (boot the necessary image on a remote machine or launch a new Hyper-V or
Azure VM, etc.) for the tests.

However, this use of pytest-dist requires full Python support on the target
machines, and drastically changes how developers write tests. Furthermore, it
would not support running local commands against the remote node (like ping) or
running the test across a reboot of the node. Thus we do not want to use this
functionality of pytest-xdist. That said, pytest-xdist will still be useful for
running tests concurrently, as described above.

### Using Paramiko Instead of Fabric

The Paramiko library is less complex (smaller library footprint) than Fabric, as
the latter wraps the former, but it is a bit more difficult to use, and doesn’t
support reading existing SSH config files, nor does it support “ProxyJump” which
we use heavily. Fabric instead provides a clean high-level interface for
existing shell commands, handling all the connection abstractions for us.

Using Paramiko looked like this:

```python
from pathlib import Path
from typing import List

from paramiko import SSHClient

import pytest

@pytest.fixture
def node() -> SSHClient:
    with SSHClient() as client:
        client.load_system_host_keys()
        client.connect(hostname="...")
        yield client


def test_lis_version(node: SSHClient) -> None:
    with node.open_sftp() as sftp:
        for f in ["utils.sh", "LIS-VERSION-CHECK.sh"]:
            sftp.put(LINUX_SCRIPTS / f, f)
        _, stdout, stderr = node.exec_command("./LIS-VERSION-CHECK.sh")
        sftp.get("state.txt", "state.txt")
    with Path("state.txt").open as f:
        assert f.readline() == "TestCompleted"
```

It is more verbose than necessary when compared to Fabric.

### StringIO

For `Node.cat()` it would seem we could use `StringIO` like so:

```python
from io import StringIO

with StringIO() as result:
    node.get("state.txt", result)
    assert result.getvalue().strip() == "TestCompleted"
```

However, the data returned by Paramiko is in bytes, which in Python 3 are not
equivalent to strings, hence the existing implementation which uses `BytesIO`
and decodes the bytes to a string.

### Writing a Class of Individual Test Methods

An option I explored to make an “executive summary” of the smoke test was to use
a class where each functionality was tested as individual function (meaning they
could fail independently without failing the whole smoke test), accompanied by a
class-scoped node fixture. This had its advantages, however, it was difficult to
parameterize and also overly verbose. We should instead keep each test as Pytest
intends: as a function. This allows the fixtures to be written in a simpler
manner (not rely on caching between functions) and allows
[parameterization](https://docs.pytest.org/en/stable/parametrize.html) using the
built-in decorator `@pytest.mark.parametrize`.

However, this decision may be reconsidered if we session-scope and parameterize
the `Node` fixture, in which case these issues are resolved.

## What Else?

There’s still a lot more to think about and design. A non-exhaustive list of
future topics (some touched on above):

* Tests inventory (generating statistics from metadata)
* ARM template support (with Azure CLI)
* Servicing Azure CLI (how stable is their API?)
* libvirt driver support (gives us Hyper-V and more)
* Duration reporting (built-in)
* Self-documentation (via Pydoc)
* Environment class design
* Feature requests (NICs in particular)
* Selection and targets YAML schema
* Secret management
* External results reporting (database and emails)
* Embedded systems / bare metal support
* Managing Python `logging` records
* Managing shell command stdout/stderr