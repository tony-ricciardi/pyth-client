#include <pc/ext/verify.hpp>

#include <sstream>

namespace pc
{
  char const* assertion_error::what() const noexcept
  {
    tmp_msg_ = msg_.str();
    return tmp_msg_.c_str();
  }

  assertion_error assertion_error::standard(
    char const* const expr
    , char const* const file
    , int const line
  ) {
    // Same format as cassert.
    assertion_error err;
    err.msg_ << file << ":" << line;
    err.msg_ << " failed assertion `" << expr << "`";
    return err;
  }
}
