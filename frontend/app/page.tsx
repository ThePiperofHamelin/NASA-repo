export default function Home() {
  return (
    <>
      <div id="loading">Loading...</div>
      <div id="controller">
        <div>
          <span>Coordinates: </span>
          <input id="coord-x" type="number" min="-1000" max="1000" step="0.01" placeholder="X" />
          <input id="coord-y" type="number" min="-1000" max="1000" step="0.01" placeholder="Y" />
        </div>
        <div>
          <label htmlFor="band">Band:</label>
          <select id="band">
            <option value="radio">Radio</option>
            <option value="ir">IR</option>
            <option value="visible">Visible</option>
            <option value="uv">UV</option>
          </select>
        </div>
      </div>
      <div id="image"></div>
    </>
  );
}

function $<T extends HTMLElement = HTMLElement>(x: string): T {
  const e = document.querySelector<T>(x);
  if (e == null)
    throw new Error("Element not found: " + x);

  return e;
}

async function load_image(img: HTMLElement, x: number, y: number, band: string) {
  const res = await fetch("http://{backend_host}/api/getPic?ra=" + x + "&dec=" + y);
  if (res == null || !res.ok) {
    console.error("Fetch error: ");
    return false;
  }

  const tmpUrl  =URL.createObjectURL(await res.blob());

  const elem = document.createElement("img");
  elem.src = tmpUrl;
  elem.width = 800;
  elem.height = 800;
  elem.loading = "lazy";
  elem.decoding = "async";
  elem.draggable = false;
  img.appendChild(elem);


  try {
    await elem.decode();
  URL.revokeObjectURL(tmpUrl);
  } catch (err) {
    console.error("Decoding error: ", err);
  }

  return true;
}

function _init() {
  const image = $("image");
  const inpX = $("coord-x") as HTMLInputElement;
  const inpY = $("coord-y") as HTMLInputElement;
  const band = $("band") as HTMLSelectElement;

  (inpX.onchange = inpY.onchange = band.onchange = () => {
    load_image(image, parseFloat(inpX.value) || 0, parseInt(inpY.value) || 0, band.value || "");
  })();
}

document.addEventListener("DOMContentLoaded", _init, { once: true, passive: true });
