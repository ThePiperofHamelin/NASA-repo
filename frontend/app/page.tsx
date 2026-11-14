'use client';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useEffect, useState } from 'react';

export default function Home() {
  const [imgUrl, setImgUrl] = useState(
    'http://localhost:8000/api/getPic?ra=304.693508808&dec=42.4436872991&n=1'
  );
  const [ra, setRa] = useState(304.693508808); // default value
  const [dec, setDec] = useState(42.4436872991); // default value
  const [n, setN] = useState(1); // default value

  return (
    <>
      <Card className="absolute m-2 bg-white" size="sm">
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input
            placeholder="Enter RA"
            value={ra}
            onChange={(e) => setRa(Number(e.target.value))}
          />
          <Input
            placeholder="Enter Declination"
            value={dec}
            onChange={(e) => setDec(Number(e.target.value))}
          />
          <Input
            placeholder="Enter N"
            type="number"
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
          />
        </CardContent>
        <CardFooter>
          <Button
            onClick={() => {
              setImgUrl(
                `http://localhost:8000/api/getPic?ra=${ra}&dec=${dec}&n=${n}`
              );
            }}
          >
            Update image
          </Button>
        </CardFooter>
      </Card>
      <img
        className="mx-auto my-auto w-[50%] border-white border-2"
        src={imgUrl}
      />
    </>
  );
}
