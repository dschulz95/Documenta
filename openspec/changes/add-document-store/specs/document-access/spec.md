# Spec Delta

## Purpose

Makes sure only the owner, on devices in their tailnet, can reach and use the document store. The connection is HTTPS, the store has its own hostname, and there is no public exposure.

## ADDED Requirements

### Requirement: Tailnet-only reachability
The document store SHALL be reachable only through its own Tailscale node. No container of the stack SHALL publish a port on the Raspberry Pi's network interfaces, and Tailscale Funnel SHALL stay disabled.

#### Scenario: Reachable from the tailnet
- **GIVEN** a phone or PC that is logged in to the owner's tailnet
- **WHEN** it opens `https://<docs-hostname>.<tailnet>.ts.net`
- **THEN** the Nextcloud login page loads over HTTPS with a valid certificate

#### Scenario: Not reachable from the LAN
- **GIVEN** a device on the home network that is not in the tailnet
- **WHEN** it connects to any port on the Pi's LAN IP address
- **THEN** no document store service answers

#### Scenario: Not reachable from the internet
- **WHEN** a device outside the tailnet resolves or connects to the docs hostname
- **THEN** the connection fails

### Requirement: HTTPS only
The document store SHALL serve all traffic over HTTPS on its tailnet hostname. Links, redirects, and client configuration that the server generates SHALL use that HTTPS URL.

#### Scenario: Generated links use the tailnet URL
- **WHEN** the owner copies a file's internal link in the web UI
- **THEN** the link starts with `https://<docs-hostname>.<tailnet>.ts.net/`

#### Scenario: Unknown host name rejected
- **WHEN** a request reaches the server with a host name other than the configured tailnet hostname
- **THEN** the server refuses it as an untrusted domain

### Requirement: Owner account
On first start, the stack SHALL create exactly one administrator account. Its username and password SHALL come from the environment configuration. Self-registration SHALL NOT be possible.

#### Scenario: First start creates the owner
- **GIVEN** an empty data folder and database
- **WHEN** the stack starts with the owner username and password set
- **THEN** the owner can log in with those credentials

#### Scenario: No sign-up
- **WHEN** a visitor opens the login page
- **THEN** there is no way to create an account

### Requirement: Login required
Every file operation SHALL require an authenticated session or an app password. Repeated failed logins from one address SHALL be slowed down or blocked.

#### Scenario: Anonymous request rejected
- **WHEN** a request without valid credentials asks to list or download a file
- **THEN** the server answers with an authentication error and returns no file data

#### Scenario: Brute-force protection
- **WHEN** one address fails to log in more than 10 times within 30 minutes
- **THEN** further login attempts from that address are refused, even with the correct password
- **AND** logins work again once the block expires or the owner lifts it

### Requirement: No public sharing
The document store SHALL NOT allow creating public share links. Files SHALL only be reachable by authenticated users.

#### Scenario: Public link option unavailable
- **WHEN** the owner opens the sharing options of a file
- **THEN** there is no option to create a public link
