import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';

export default function Home() {
  return (
    <>
      <Card className="absolute m-2 bg-white" size="sm">
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input placeholder="Enter RA" />
          <Input placeholder="Enter Declination" />
        </CardContent>
        <CardFooter>
          <Button>Update image</Button>
        </CardFooter>
      </Card>
      <img
        className="mx-auto my-auto w-[50%] border-white border-2"
        src="http://localhost:8000/api/getPic?ra=304.693508808&dec=42.4436872991"
      />
    </>
  );
}
