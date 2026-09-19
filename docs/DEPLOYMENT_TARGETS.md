# DEPLOYMENT_TARGETS.md

Running the kit beyond a developer workstation: containers, VMs, and
Kubernetes for scaled cloud implementations. The kit's substance — the ledger,
the wall, the roster, the procedures — is plain files and stdlib Python, so
every target below changes only **who runs the timer, who serves the wall, and
who ships the telemetry**. Nothing else moves.

The invariants that hold on every target, and what each one forbids:

| Invariant | Consequence on any target |
|---|---|
| The ledger is files in the repo checkout | The working volume must persist across restarts, or shards ship before shutdown |
| One sweeper per checkout | Two timers on one `.wall/` is the corruption the machine-wide-timer design exists to prevent |
| The wall server is unauthenticated by design | It is never exposed beyond a trusted boundary — localhost, pod, or private network with its own auth in front |
| The telemetry branch has one writer | Multiple shippers to one branch clobber each other; scale readers, not writers |
| Installs are consent-gated | Baking the schedule into an image or manifest **is** the consent — the engineer applies the manifest |

---

## 1. Docker (single container or sidecar)

A container image needs: Python 3.11+, git (for `wall ship`/`fetch`), and the
repo checkout. No pip installs — the kit is stdlib-only.

**The timer becomes the container's loop.** The OS-level adapters (schtasks /
launchd / systemd) do not apply inside a container; the honest equivalent is a
loop process or the host's scheduler running:

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY . .
# Sweep + ship loop. run-once also refreshes .wall/derived/doctor.json,
# so the shipped telemetry carries plumbing + roster health with it.
CMD ["sh", "-c", "while true; do \
      python3 tools/wall/wall.py --repo /repo run-once; \
      python3 tools/wall/shipper.py --repo /repo --ship || true; \
      sleep 120; done"]
```

- **Serving:** `wall serve` binds `127.0.0.1` *inside the container*. Publish
  it only to the host's loopback: `docker run -p 127.0.0.1:8123:8123 ...` and
  run `serve` with the container's port published — never `-p 8123:8123`
  (that is `0.0.0.0` on the host, the exact exposure the bind exists to
  prevent). For anything wider, put an authenticating reverse proxy in front.
- **Persistence:** mount the checkout (`-v $PWD:/repo`) or accept that the
  container's shards live only as long as the container plus what `ship`
  pushed. Shipping every sweep makes an ephemeral container safe.
- **As a sidecar:** in a compose file, one wall-courier service beside the
  app services, sharing the repo volume read-write while everything else
  mounts it read-only.
- **Git identity + credentials:** provide them per-invocation
  (`GIT_AUTHOR_*`/`GIT_COMMITTER_*` env, a mounted credential helper or a
  deploy token scoped to the telemetry branch). Never bake a token into the
  image; never write `git config` from inside (G1 applies to containers too).

## 2. VMs

A VM is a machine: `wall install` works exactly as on hardware — systemd user
timers on Linux VMs, the scheduled task on Windows VMs. Two VM-specific notes:

- **Suspended clocks:** a VM that sleeps produces heartbeat gaps that look
  like dead timers. `Persistent=true` (already in the systemd unit) fires the
  missed run on resume; treat a red `generated_at` right after resume as
  expected, not as a failure to chase.
- **Golden images:** an image with the timer pre-installed carries the
  consent decision with it. Record that as a decision (`DEC-NNNN`: "the
  image installs the courier timer; applying the image is the consent"), so
  the SessionStart detect-only rule still reads coherently on cloned VMs.

## 3. Kubernetes (scaled cloud)

Kubernetes replaces the machine-wide timer with a **CronJob** and the local
server with a **Deployment behind a ClusterIP**. The ledger's home moves to a
PersistentVolumeClaim holding the checkout.

```yaml
# One sweeper per checkout: the CronJob IS the machine-wide timer.
apiVersion: batch/v1
kind: CronJob
metadata: {name: wall-courier}
spec:
  schedule: "*/2 * * * *"
  concurrencyPolicy: Forbid        # a slow sweep must not overlap the next
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
          - name: courier
            image: <your-kit-image>
            command: ["sh", "-c",
              "python3 tools/wall/wall.py --repo /repo run-once && \
               python3 tools/wall/shipper.py --repo /repo --ship || true"]
            volumeMounts: [{name: repo, mountPath: /repo}]
          volumes:
          - {name: repo, persistentVolumeClaim: {claimName: wall-repo}}
---
# The wall, read-only, inside the cluster only.
apiVersion: apps/v1
kind: Deployment
metadata: {name: wall-server}
spec:
  replicas: 1
  selector: {matchLabels: {app: wall-server}}
  template:
    metadata: {labels: {app: wall-server}}
    spec:
      containers:
      - name: server
        image: <your-kit-image>
        command: ["python3", "tools/wall/wall.py", "--repo", "/repo",
                  "serve", "--port", "8123"]
        volumeMounts: [{name: repo, mountPath: /repo, readOnly: true}]
      volumes:
      - {name: repo, persistentVolumeClaim: {claimName: wall-repo}}
---
apiVersion: v1
kind: Service
metadata: {name: wall}
spec: {type: ClusterIP, selector: {app: wall-server}, ports: [{port: 8123}]}
```

Rules that keep the scaled shape honest:

- **`concurrencyPolicy: Forbid`** is the "one sweeper per checkout" invariant
  in manifest form. Do not raise CronJob parallelism; scale by adding
  *checkouts* (one PVC + CronJob pair per repo), which is exactly the
  machine-registry model with namespaces as machines.
- **The Service stays ClusterIP.** The wall server has no auth by design; an
  Ingress in front of it publishes the full event history. Reach it with
  `kubectl port-forward svc/wall 8123:8123` (the cluster's equivalent of
  localhost), or front it with an authenticating proxy you own.
- **One shipper.** Only the CronJob ships. Agent sessions running in other
  pods write their own session shards to their own checkout and ship on their
  own branch, or mount the shared PVC — never both.
- **Consent** is the manifest: applying it is the engineer's `--yes`. The
  SessionStart hook's detect-only rule holds — a session in a pod reports a
  missing CronJob to the engineer with the manifest, it does not
  `kubectl apply` on its own (the LLM_BOOTSTRAP "ASK THE ENGINEER (run)"
  boundary, cluster edition).
- **Secrets** (git credentials for `ship`) come from a Kubernetes Secret
  scoped to the telemetry branch, mounted into the CronJob only — the server
  pod needs none.

## 4. Choosing

| Situation | Target |
|---|---|
| One engineer, one machine | Native install (INSTALL.md) — the default, least moving parts |
| The repo already runs in compose | Courier as a sidecar service |
| CI-only wall (render on every push, no live serve) | `wall run-once` as a pipeline step; publish `wall.html` as an artifact |
| Many repos, one box | Still native — the machine-wide registry exists exactly for this |
| Cloud, many repos, team-visible walls | Kubernetes: one PVC + CronJob per repo, ClusterIP serving, port-forward or authed proxy to read |

Whatever the target: the procedures (WORKFLOW, SESSION_LIFECYCLE, the SOPs)
do not change at all. Only the timer, the serve boundary, and the shipping
credentials moved.
