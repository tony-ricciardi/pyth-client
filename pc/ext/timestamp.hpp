#pragma once

#include <cstdint>

namespace pc
{
  // Require explicit conversion between ts and ns.
  using timestamp = uint64_t;
  using nsecs = int64_t;

  inline constexpr nsecs NS_PER_US{ 1000 };
  inline constexpr nsecs NS_PER_MS{ NS_PER_US * 1000 };
  inline constexpr nsecs NS_PER_SEC{ NS_PER_MS * 1000 };
  inline constexpr nsecs NS_PER_MIN{ NS_PER_SEC * 60 };
  inline constexpr nsecs NS_PER_HOUR{ NS_PER_MIN * 60 };
  inline constexpr nsecs NS_PER_DAY{ NS_PER_HOUR * 24 };
  inline constexpr nsecs NS_PER_YEAR{ NS_PER_DAY * 365 };

  constexpr nsecs as_ns( timestamp const ts )
  {
    return static_cast< nsecs >( ts );
  }

  constexpr timestamp add_time( timestamp const ts, nsecs const ns )
  {
    return static_cast< timestamp >( as_ns( ts ) + ns );
  }

  constexpr nsecs diff_times( timestamp const ts1, timestamp const ts2 )
  {
    return as_ns( ts1 ) - as_ns( ts2 );
  }

  constexpr timestamp floor_time( timestamp const ts, nsecs const interval )
  {
    return static_cast< timestamp >( as_ns( ts ) / interval * interval );
  }
}
