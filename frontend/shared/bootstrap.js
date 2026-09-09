const ASSET_VERSION = "stage4-provider-resolution-1";
const asset = (path) => `${path}?v=${ASSET_VERSION}`;

if (window.location.pathname === "/app/invitations/accept") {
  const activation = await import(asset("/assets/app/activation.js"));
  activation.start();
} else {
  const surface = window.location.pathname.startsWith("/system") ? "system" : "app";
  const entrypoint = await import(asset(`/assets/${surface}/entry.js`));
  entrypoint.start();
}
