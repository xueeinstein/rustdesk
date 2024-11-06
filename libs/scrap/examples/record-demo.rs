use clap::Parser;
use rdev::{listen, Event};
use scrap::{
    codec::{EncoderApi, Quality},
    vpxcodec, Capturer, Display, TraitCapturer, STRIDE_ALIGN,
};
use std::{
    error::Error,
    fs::{File, OpenOptions},
    io::{self, BufWriter, Write},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};
use tokio::sync::mpsc;
use webm::mux::{self, Track};

/// A cli program to record demo: screen + action recording
#[derive(Parser, Debug)]
struct Args {
    /// Output webm path
    #[arg(short, long)]
    webm_path: PathBuf,

    /// Output action log
    #[arg(short, long)]
    act_log: PathBuf,

    /// FPS
    #[arg(short, long, default_value_t = 30)]
    fps: u64,
}

struct DemoCapture {
    webm_file: File,
    // action_file: File,
    action_log: PathBuf,
    fps: u64,
}

impl DemoCapture {
    fn new(args: Args) -> Result<Self, Box<dyn Error>> {
        let webm_file = Self::_create_file(&args.webm_path)?;
        // let action_file = Self::_create_file(&args.act_log)?;

        Ok(DemoCapture {
            webm_file,
            // action_file,
            action_log: args.act_log,
            fps: args.fps,
        })
    }

    async fn record(&mut self) -> io::Result<()> {
        let action_file = Self::_create_file(&self.action_log).unwrap();
        let mut act_buf = BufWriter::new(action_file);

        let mut webm_writer = mux::Segment::new(mux::Writer::new(&self.webm_file))
            .expect("Could not initialize the multiplexer.");

        let vpx_codec = vpxcodec::VpxVideoCodecId::VP9;
        let mux_codec = mux::VideoCodecId::VP9;

        let display = Display::primary().unwrap();
        let (width, height) = (display.width() as u32, display.height() as u32);
        let mut vt = webm_writer.add_video_track(width, height, None, mux_codec);

        let mut vpx =
            vpxcodec::VpxEncoder::new(scrap::codec::EncoderCfg::VPX(vpxcodec::VpxEncoderConfig {
                width,
                height,
                quality: Quality::Best,
                codec: vpx_codec,
                keyframe_interval: None,
            }), true)
            .unwrap();

        let mut screen_capturer = Capturer::new(display).unwrap();

        let sleep_per_frame = Duration::from_nanos(1_000_000_000 / self.fps);

        let (action_sender, mut action_receiver) = mpsc::unbounded_channel::<Event>();

        let stop = Arc::new(AtomicBool::new(false));
        let stop_act = Arc::new(AtomicBool::new(false));
        let start = Instant::now();

        thread::spawn({
            let stop = stop.clone();
            let stop_act = stop_act.clone();
            move || {
                let _ = quest::ask("Recording! Press ⏎ to stop.");
                let _ = quest::text();

                thread::sleep(Duration::from_secs(3));
                stop_act.store(true, Ordering::Release);
                stop.store(true, Ordering::Release);
            }
        });

        thread::spawn(move || {
            listen(move |event| {
                action_sender
                    .send(event)
                    .unwrap_or_else(|e| println!("Could not send event: {:?}", e));
            })
            .expect("Could not listen");
        });

        tokio::task::spawn(async move {
            while {
                !stop_act.load(Ordering::Acquire)
            }{
                if let Some(e) = action_receiver.recv().await {
                    println!("Received {:?}", e);

                    let now = Instant::now();
                    let time = now - start;
                    let ms = time.as_secs() * 1000 + time.subsec_millis() as u64;

                    let data = format!("ms:{},event_type:{:?}\n", ms, e.event_type);
                    let _ = act_buf.write(data.as_bytes());
                    let _ = act_buf.flush();
                }
            }
        });

        while !stop.load(Ordering::Acquire) {
            let now = Instant::now();
            let time = now - start;

            match screen_capturer.frame(Duration::from_millis(0)) {
                Ok(frame) => {
                    let ms = time.as_secs() * 1000 + time.subsec_millis() as u64;
                    println!(">>> {}", ms);

                    let mut yuv = Vec::new();
                    let mut mid_data = Vec::new();
                    frame.to(vpx.yuvfmt(), &mut yuv, &mut mid_data).unwrap();
                    for frame in vpx.encode(ms as i64, &yuv, STRIDE_ALIGN).unwrap() {
                        vt.add_frame(frame.data, frame.pts as u64 * 1_000_000, frame.key);
                    }
                }
                Err(e) => eprintln!("Failed to capture frame: {}", e),
            }

            let dt = now.elapsed();
            if dt < sleep_per_frame {
                thread::sleep(sleep_per_frame - dt);
            }
        }

        vpx.flush().unwrap();
        webm_writer.finalize(None);
        // act_buf.flush()?;
        Ok(())
    }

    fn _create_file(path: &PathBuf) -> Result<File, Box<dyn Error>> {
        match OpenOptions::new().write(true).create_new(true).open(path) {
            Ok(file) => Ok(file),
            Err(ref e) if e.kind() == io::ErrorKind::AlreadyExists => {
                if loop {
                    quest::ask(&format!(
                        "Overwrite the existing file {} ? [y/N] ",
                        path.to_string_lossy()
                    ));
                    if let Some(b) = quest::yesno(false)? {
                        break b;
                    }
                } {
                    Ok(File::create(path)?)
                } else {
                    return Err(format!(
                        "File {} already exists and won't be overwritten.",
                        path.to_string_lossy()
                    )
                    .into());
                }
            }
            Err(e) => return Err(e.into()),
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let args = Args::parse();
    let mut demo_capture = DemoCapture::new(args)?;
    let _ = demo_capture.record().await;
    println!("Done");
    Ok(())
}
