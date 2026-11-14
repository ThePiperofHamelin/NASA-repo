export default function Img({ src }: { src: string }) {
  return (
    <img alt="" className="mx-auto my-auto w-[50%] border-white border-2" src={src} />
  );
}
