#[unsafe(no_mangle)]
pub extern "C" fn tcolor_ramp_rust_link() {
    #[cfg(tcolor_ramp_native)]
    unsafe {
        tcolor_ramp_keepalive();
    }
}

#[cfg(tcolor_ramp_native)]
unsafe extern "C" {
    fn tcolor_ramp_keepalive();
}
