# Security

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Report it privately through
GitHub's [private advisory form](<repo-url>/security/advisories/new), or by
email to <contact>.

Include the version, the steps to reproduce, and what an attacker gains. Expect
an acknowledgement within a few days. Credit is given in the release notes
unless you ask otherwise.

## Scope

In scope:

- <the surface where a bug means someone reads, writes or executes what they
  should not>

Out of scope:

- <the things that look like bugs but are documented behaviour>

## Deploy checklist

<!-- Every variable that fails closed belongs here. If a missing value makes
     the service refuse to start, say so, because that is the behaviour a
     deployer needs to expect. -->

Before running this in an environment other people can reach:

- [ ] <secret> is set and is not the default
- [ ] The service binds to localhost, or a proxy terminates TLS in front of it
- [ ] <anything that fails closed is documented above>
- [ ] Logs are written somewhere with a retention policy
- [ ] A kill switch exists and has been tested

## Known limitations

<!-- Name them. A limitation stated is one a deployer can weigh. A limitation
     discovered later is a reason to stop trusting the project. -->

- <limitation, and what it means for a deployer>
