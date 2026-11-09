# Countdown — quality rubric

The bundle is graded on what it promises, and every line below is checkable
against the manifest, the served bytes, or the tool's own reply.

- **One surface, named.** The manifest declares exactly one `components.ui`
  descriptor, and the document at that entry is what the mount answers. A title
  the shell can read, a size inside the contract's ceiling, and no second entry
  hiding behind the first.
- **Nothing leaves the bundle.** The page loads its own script and its own
  stylesheet through the surface path. No remote host is fetched, no CDN is
  consulted, and the content security policy the route emits was assembled from
  declared capabilities only.
- **The agent's ask lands on the tool.** A request to start or read the timer is
  answered by the countdown's tool call, with the remaining time in the reply, so
  the surface and the tool agree on one state.
- **The state stays in the plugin's own folder.** The timer the tool writes lives
  under the declared data root, and a plugin switched off leaves nothing running
  behind it.
- **Every declaration is read.** The capabilities the manifest names are inside
  the closed vocabulary, and the contract's enforcement table says out loud which
  of them a layer confines today. A name nothing watches yet is recorded as
  unenforced there, and the page does not claim it exercised it.
